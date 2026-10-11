"""Perceptual similarity gating - keep only the strongest near-duplicate variants.

Adobe's distinct-content rules refuse batches where several images are visual
variants of the same shot. A generative model asked for twenty variants of one
prompt happily emits them, so the pipeline needs a gate that runs *inside* a
batch: cluster visually similar images, keep the sharpest ``keep_top`` of each
cluster, and set the rest aside for a future batch (or drop them).

Signals (reusing :mod:`services.duplicate_detector` so the thresholds match the
existing similarity scan):

* **Similarity** - 64-bit dHash Hamming distance normalised to 0-1. Two images
  are "the same shot" at ``similarity >= threshold`` (default 0.85).
* **Quality score** - variance of the Laplacian on grayscale: the standard
  cheap sharpness proxy. The sharpest variants survive; soft duplicates go.

Clustering is union-find (single linkage) over the pairwise similarity graph,
so chains of near-identical variants land in one cluster even when the ends
are marginally apart. Deterministic: ties in quality break by record id.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from services.duplicate_detector import dhash, visual_similarity

logger = logging.getLogger(__name__)

#: Default similarity at or above which two images count as the same shot.
DEFAULT_SIMILARITY_THRESHOLD = 0.85
#: Variants kept per similarity cluster (sharpest first).
DEFAULT_KEEP_TOP = 2


@dataclass
class VariantScore:
    """Everything the gate knows about one image."""

    record_id: str
    path: Path
    phash: int = 0
    sharpness: float = 0.0
    readable: bool = True
    cluster: int = -1
    rank: int = 0
    keep: bool = True
    similarities: dict[str, float] = field(default_factory=dict)


def score_image(record_id: str, path: Path | str) -> VariantScore:
    """Hash + sharpness for one file. Unreadable files are marked, never raised.

    An unreadable file is *kept* by the gate: it cannot be shown similar to
    anything, and dropping a broken file from its own batch would hide the
    breakage behind a quarantine nobody checks.
    """
    score = VariantScore(record_id=record_id, path=Path(path))
    try:
        image = cv2.imread(str(score.path), cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001 - one bad file must not stop the batch
        logger.exception("Could not read %s for diversity gating", score.path)
        image = None
    if image is None:
        score.readable = False
        logger.warning("Could not decode %s for diversity gating", score.path)
        return score

    score.phash = dhash(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    score.sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return score


def _find(parents: list[int], i: int) -> int:
    while parents[i] != i:
        parents[i] = parents[parents[i]]  # path compression
        i = parents[i]
    return i


def _union(parents: list[int], a: int, b: int) -> None:
    ra, rb = _find(parents, a), _find(parents, b)
    if ra != rb:
        parents[rb] = ra


def build_plan(
    scores: list[VariantScore],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    keep_top: int = DEFAULT_KEEP_TOP,
) -> list[VariantScore]:
    """Cluster similar variants and decide keep/quarantine for each score.

    Mutates and returns ``scores``. Records in different clusters are all kept;
    within a cluster the ``keep_top`` sharpest survive (``keep_top <= 0`` keeps
    nothing - the whole cluster is set aside).
    """
    n = len(scores)
    if n == 0:
        return scores

    parents = list(range(n))
    for i in range(n):
        if not scores[i].readable:
            continue
        for j in range(i + 1, n):
            if not scores[j].readable:
                continue
            sim = visual_similarity(scores[i].phash, scores[j].phash)
            if sim >= threshold:
                scores[i].similarities[scores[j].record_id] = round(sim, 4)
                scores[j].similarities[scores[i].record_id] = round(sim, 4)
                _union(parents, i, j)

    # Group cluster members, deterministic order: sharpest first, id tiebreak.
    clusters: dict[int, list[VariantScore]] = {}
    for idx, score in enumerate(scores):
        root = _find(parents, idx) if score.readable else -idx - 1
        score.cluster = root
        clusters.setdefault(root, []).append(score)

    for members in clusters.values():
        members.sort(key=lambda s: (-s.sharpness, s.record_id))
        for rank, member in enumerate(members):
            member.rank = rank
            member.keep = rank < keep_top

    return scores


def gate_batch(
    entries: list[tuple[str, Path | str]],
    *,
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    keep_top: int = DEFAULT_KEEP_TOP,
) -> dict[str, dict]:
    """Full pass for a batch: score, cluster, decide.

    Args:
        entries: ``(record_id, path)`` pairs for the batch's current files.

    Returns:
        ``record_id -> plan dict`` with ``keep``, ``reason``, ``cluster``,
        ``rank``, ``sharpness``, ``similarity_threshold`` and, for quarantined
        records, ``kept_over`` (the record ids that outranked it).
    """
    scores = [score_image(rid, path) for rid, path in entries]
    scores = build_plan(scores, threshold=threshold, keep_top=keep_top)

    cluster_peaks: dict[int, list[VariantScore]] = {}
    for score in scores:
        if score.keep:
            cluster_peaks.setdefault(score.cluster, []).append(score)

    plan: dict[str, dict] = {}
    for score in scores:
        peaks = cluster_peaks.get(score.cluster, [])
        kept_over = [p.record_id for p in peaks if p.rank < score.rank]
        clustered = len({s.record_id for s in scores if s.cluster == score.cluster}) > 1
        if not score.readable:
            reason = "Unreadable file - kept (needs manual review)."
        elif score.keep and clustered:
            reason = (
                f"Kept: sharpest of {sum(1 for s in scores if s.cluster == score.cluster)} "
                f"similar variants (rank {score.rank + 1})."
            )
        elif score.keep:
            reason = "Kept: no similar variants in this batch."
        else:
            reason = (
                f"Quarantined: variant {score.rank + 1} of a similar cluster; "
                f"{len(kept_over)} sharper variant(s) kept."
            )
        plan[score.record_id] = {
            "keep": score.keep,
            "readable": score.readable,
            "reason": reason,
            "cluster": score.cluster,
            "rank": score.rank,
            "sharpness": round(score.sharpness, 2),
            "similarity_threshold": threshold,
            "keep_top": keep_top,
            "similarities": score.similarities,
            "kept_over": kept_over,
        }
    return plan
