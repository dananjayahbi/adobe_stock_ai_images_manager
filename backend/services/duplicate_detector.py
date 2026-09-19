"""Near-duplicate detection - Adobe's most common content-refusal reason.

Adobe's distinct-content guidance is unusually blunt: *"Similar content is one
of the top reasons we refuse content submitted to Adobe Stock."* It counts as
too similar when submissions share:

* **Subject and composition** - the same subject from slightly different angles.
* **Creative treatment** - one concept with minor colour/filter variation.
* **Series submissions** - sequential shots with minimal meaningful difference.
* **Metadata patterns** - different images tagged with identical titles and
  keywords.

The last point is the one an automated pipeline can catch cheaply and reliably,
and it is also the one this app is most likely to produce: a generative model
asked for twenty variants of the same prompt will emit twenty near-identical
titles.

Two complementary signals are computed here:

1. **Perceptual hash distance** (``dhash``) for pixel similarity. Cheap, no
   dependencies beyond OpenCV, and robust to re-encoding.
2. **Metadata similarity** (token-set Jaccard on title + keywords) for the
   "identical titles and keywords" pattern.

Both are advisory. The module never deletes or blocks anything - it returns
groups so an operator can pick the strongest few, which is exactly what Adobe
asks for: *"Select your strongest three to five photos per subject, angle, or
pose."*

Source: helpx /submit-distinct-content/distinct-content-submission-best-practices.html
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: 64-bit difference hash, so two images are at most 64 bits apart.
_HASH_BITS = 64
#: Hamming distance at or below which two images are considered visually
#: near-identical. 6/64 is the usual "same shot" threshold; 10/64 catches the
#: minor-angle variants Adobe explicitly calls out.
VISUAL_DUPLICATE_DISTANCE = 6
VISUAL_SIMILAR_DISTANCE = 12

#: Jaccard similarity of the title+keyword token sets above which two records
#: are flagged for reusing metadata, which Adobe lists as its own refusal cause.
METADATA_SIMILARITY_THRESHOLD = 0.72

_WORD = re.compile(r"[a-z0-9]+")
#: Words carrying no discriminating information about *this* image.
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "the", "of", "in", "on", "at", "with", "for", "to",
        "by", "from", "as", "is", "are", "be", "or", "into", "over", "under",
        "background", "image", "photo", "photograph", "picture", "shot",
    }
)


def dhash(image_bgr: np.ndarray, hash_size: int = 8) -> int:
    """Compute a difference hash for a BGR image.

    ``dhash`` compares each pixel with its right-hand neighbour on a
    ``hash_size + 1`` wide grayscale thumbnail. It is stable under resizing and
    JPEG re-encoding, which is what makes it usable on this pipeline's own
    refined output.

    Args:
        image_bgr: BGR ``uint8`` array.
        hash_size: Bits per axis; 8 yields a 64-bit hash.

    Returns:
        The hash as an integer.
    """
    if image_bgr is None or image_bgr.size == 0:
        return 0

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    # Resize to (width, height) = (hash_size + 1, hash_size).
    resized = cv2.resize(
        gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA
    )
    diff = resized[:, 1:] > resized[:, :-1]

    value = 0
    for bit in diff.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming_distance(left: int, right: int) -> int:
    """Number of differing bits between two hashes."""
    return int(bin(left ^ right).count("1"))


def visual_similarity(left: int, right: int) -> float:
    """Normalise hash distance to a 0-1 similarity score."""
    return 1.0 - (hamming_distance(left, right) / _HASH_BITS)


def tokenize_metadata(title: str | None, keywords: list[str] | None) -> frozenset[str]:
    """Reduce a record's metadata to a discriminating token set."""
    parts: list[str] = []
    if title:
        parts.append(title)
    if keywords:
        parts.extend(str(keyword) for keyword in keywords)

    tokens = {
        token
        for token in _WORD.findall(" ".join(parts).lower())
        if token not in _STOPWORDS and len(token) > 1
    }
    return frozenset(tokens)


def metadata_similarity(
    left: frozenset[str], right: frozenset[str]
) -> float:
    """Jaccard similarity between two token sets (0 when either is empty)."""
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


@dataclass
class DuplicatePair:
    """A pair of records that Adobe would likely consider too similar."""

    left_id: str
    right_id: str
    visual_score: float
    metadata_score: float
    #: ``visual`` | ``metadata`` | ``both``
    reason: str

    def to_dict(self) -> dict:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "visual_score": round(self.visual_score, 4),
            "metadata_score": round(self.metadata_score, 4),
            "reason": self.reason,
        }


@dataclass
class DuplicateGroup:
    """A cluster of mutually similar records, plus the ones to keep."""

    record_ids: list[str]
    reason: str
    #: The ids worth submitting - Adobe advises three to five per subject.
    suggested_keep: list[str] = field(default_factory=list)
    #: The rest, which are candidates for dropping from the submission.
    suggested_drop: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "record_ids": list(self.record_ids),
            "reason": self.reason,
            "suggested_keep": list(self.suggested_keep),
            "suggested_drop": list(self.suggested_drop),
        }


@dataclass
class DuplicateCandidate:
    """Input to the duplicate scan - only what the analysis needs."""

    record_id: str
    hash_value: int
    tokens: frozenset[str]


def find_duplicate_pairs(
    candidates: list[DuplicateCandidate],
    *,
    visual_distance: int = VISUAL_SIMILAR_DISTANCE,
    metadata_threshold: float = METADATA_SIMILARITY_THRESHOLD,
) -> list[DuplicatePair]:
    """Find every pair of candidates that look or read as too similar.

    Args:
        candidates: Hashes and metadata tokens for the records to compare.
        visual_distance: Hamming distance at or below which images are flagged.
        metadata_threshold: Jaccard similarity at or above which metadata is
            considered reused.

    Returns:
        Pairs that tripped either signal, strongest first.
    """
    pairs: list[DuplicatePair] = []

    for left, right in combinations(candidates, 2):
        # A hash of 0 is the sentinel for "could not read this image". Two
        # unreadable files both hash to 0, so comparing them would report a
        # perfect visual match between images that were never actually seen.
        # The visual signal is therefore skipped unless both hashes are real.
        hashes_known = left.hash_value != 0 and right.hash_value != 0

        if hashes_known:
            distance = hamming_distance(left.hash_value, right.hash_value)
            visual = 1.0 - (distance / _HASH_BITS)
            visual_hit = distance <= visual_distance
        else:
            distance = _HASH_BITS
            visual = 0.0
            visual_hit = False

        meta = metadata_similarity(left.tokens, right.tokens)
        meta_hit = meta >= metadata_threshold
        if not (visual_hit or meta_hit):
            continue

        if visual_hit and meta_hit:
            reason = "both"
        elif visual_hit:
            reason = "visual"
        else:
            reason = "metadata"

        pairs.append(
            DuplicatePair(
                left_id=left.record_id,
                right_id=right.record_id,
                visual_score=visual,
                metadata_score=meta,
                reason=reason,
            )
        )

    pairs.sort(
        key=lambda pair: (pair.visual_score + pair.metadata_score) / 2,
        reverse=True,
    )
    return pairs


def group_duplicates(
    pairs: list[DuplicatePair],
    *,
    keep_per_group: int = 5,
) -> list[DuplicateGroup]:
    """Cluster pairs into groups via union-find and suggest what to keep.

    Adobe advises submitting "your strongest three to five photos per subject",
    so each group keeps at most ``keep_per_group`` members. Without a quality
    ranking available at this layer, the keep-set is simply the first
    ``keep_per_group`` ids in each group - callers that know the acceptance
    scores should re-order before calling.

    Args:
        pairs: Output of :func:`find_duplicate_pairs`.
        keep_per_group: Maximum ids to recommend keeping per group.

    Returns:
        One :class:`DuplicateGroup` per connected component.
    """
    if not pairs:
        return []

    parent: dict[str, str] = {}

    def find(node: str) -> str:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    reasons: dict[str, set[str]] = {}
    for pair in pairs:
        union(pair.left_id, pair.right_id)
        reasons.setdefault(pair.left_id, set()).add(pair.reason)
        reasons.setdefault(pair.right_id, set()).add(pair.reason)

    clusters: dict[str, list[str]] = {}
    for node in parent:
        clusters.setdefault(find(node), []).append(node)

    groups: list[DuplicateGroup] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        # Preserve a stable, input-independent order.
        ordered = sorted(members)
        keep = ordered[:keep_per_group]
        drop = ordered[keep_per_group:]

        group_reasons: set[str] = set()
        for member in members:
            group_reasons |= reasons.get(member, set())
        if group_reasons == {"both"} or len(group_reasons) > 1:
            reason = "both"
        elif group_reasons:
            reason = next(iter(group_reasons))
        else:
            reason = "visual"

        groups.append(
            DuplicateGroup(
                record_ids=ordered,
                reason=reason,
                suggested_keep=keep,
                suggested_drop=drop,
            )
        )

    groups.sort(key=lambda group: len(group.record_ids), reverse=True)
    return groups


def hash_image_file(path: Path | str) -> int:
    """Convenience wrapper: hash an image on disk, 0 when unreadable."""
    try:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001
        logger.exception("Could not read %s for hashing", path)
        return 0

    if image is None:
        logger.warning("Could not decode %s for hashing", path)
        return 0
    return dhash(image)
