"""Stage 4 - the image refiner.

Runs the acceptance scorer, applies the corrective recipe implied by the
reported issues, and repeats until the score clears the acceptance threshold or
the pass budget is exhausted. Each pass is measured independently because a
correction that helps one metric (sharpening) can hurt another (halo ratio).

The original file is never modified: the refiner writes a new copy into the
refined directory and returns its path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import cv2

from config import Settings, settings as default_settings
from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import AcceptanceReport
from services.refine.recipe import RefineOutcome, apply_recipe
from services.srgb_profile import write_srgb_jpeg

logger = logging.getLogger(__name__)


@dataclass
class RefineResult:
    """Outcome of a full refinement run."""

    success: bool
    output_path: str | None = None
    passes: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    report: AcceptanceReport | None = None
    history: list[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def improved(self) -> bool:
        return self.final_score > self.initial_score

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "passes": self.passes,
            "initial_score": round(self.initial_score, 4),
            "final_score": round(self.final_score, 4),
            "improved": self.improved,
            "history": self.history,
            "reason": self.reason,
            "report": self.report.to_dict() if self.report else None,
        }


def _write_jpeg(
    image, destination: Path, quality: int
) -> bool:
    """Write a BGR array as a 4:4:4 JPEG tagged with the sRGB profile.

    Adobe's photo requirements specify "JPEG with sRGB color profile", so the
    profile is embedded rather than left implicit - an untagged file is a
    documented refusal reason. The encoder lives in
    :mod:`services.srgb_profile` so the ZIP/download path and the refiner agree.
    """
    return write_srgb_jpeg(image, destination, quality)


def refine_image(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    semantic: dict | None = None,
    settings: Settings | None = None,
    config: AcceptanceConfig | None = None,
) -> RefineResult:
    """Refine an image until it clears the acceptance threshold.

    Args:
        file_path: Image to refine (never modified).
        output_dir: Directory that receives the corrected copy.
        record_id: Used to name the output file deterministically.
        semantic: Optional LLM audit dict; re-scored after every pass so a
            semantic regression is caught as quickly as a pixel regression.
        settings: Application settings override.
        config: Acceptance thresholds override.

    Returns:
        A :class:`RefineResult`. ``success`` is True when the final score
        reaches the threshold - it is False when the pass budget runs out,
        which is a legitimate "still incompatible" answer rather than an error.
    """
    cfg_settings = settings or default_settings
    cfg = config or AcceptanceConfig.from_settings()
    max_passes = max(1, int(getattr(cfg_settings, "MAX_REFINE_PASSES", 4)))
    quality = int(getattr(cfg_settings, "EXPORT_JPEG_QUALITY", 95))

    source = Path(file_path)
    if not source.exists():
        return RefineResult(False, reason=f"File not found: {file_path}")

    working, _ = _decode(source)
    if working is None:
        return RefineResult(False, reason=f"Could not decode image: {file_path}")

    report = score_image(source, config=cfg, semantic=semantic)
    initial_score = report.score
    history: list[dict] = []

    best_image = working
    best_report = report
    best_score = report.score

    if report.passed:
        # Already compliant: still emit a normalized sRGB JPEG so the rest of
        # the pipeline works from one predictable format.
        destination = Path(output_dir) / f"{record_id}-refined.jpg"
        if not _write_jpeg(working, destination, quality):
            return RefineResult(
                False,
                reason="Failed to write the normalized copy.",
                report=report,
                initial_score=initial_score,
                final_score=initial_score,
            )
        return RefineResult(
            True,
            output_path=str(destination),
            passes=0,
            initial_score=initial_score,
            final_score=initial_score,
            report=report,
            history=[
                {
                    "pass": 0,
                    "score": round(initial_score, 4),
                    "note": "Already met the acceptance threshold; normalized to sRGB JPEG.",
                }
            ],
            reason="No refinement needed.",
        )

    for pass_number in range(1, max_passes + 1):
        if not report.refinable_issues:
            # Only manual-only issues remain; more passes cannot help.
            history.append(
                {
                    "pass": pass_number,
                    "score": round(report.score, 4),
                    "note": "No automatically fixable issues remain.",
                }
            )
            break

        outcome: RefineOutcome = apply_recipe(
            working, report.refinable_issues, metrics=report.metrics
        )
        if not outcome.changed:
            history.append(
                {
                    "pass": pass_number,
                    "score": round(report.score, 4),
                    "note": "Recipe produced no changes.",
                }
            )
            break

        working = outcome.image

        # Measure the corrected array directly: it has not been written yet, so
        # the score reflects the pixels the operator will actually receive.
        candidate_path = Path(output_dir) / f"{record_id}-pass{pass_number}.jpg"
        if not _write_jpeg(working, candidate_path, quality):
            break

        report = score_image(candidate_path, config=cfg, semantic=semantic)
        history.append(
            {
                "pass": pass_number,
                "score": round(report.score, 4),
                "operations": [step.to_dict() for step in outcome.steps],
                "unaddressable": outcome.unaddressable,
            }
        )

        if report.score > best_score:
            best_score = report.score
            best_image = working
            best_report = report

        if report.passed:
            break

    # Keep only the winning pass; intermediate passes are scratch files.
    for scratch in Path(output_dir).glob(f"{record_id}-pass*.jpg"):
        scratch.unlink(missing_ok=True)

    final_destination = Path(output_dir) / f"{record_id}-refined.jpg"
    if not _write_jpeg(best_image, final_destination, quality):
        return RefineResult(
            False,
            reason="Failed to write the refined image.",
            report=best_report,
            initial_score=initial_score,
            final_score=best_score,
            history=history,
        )

    passed = best_score >= cfg.threshold
    return RefineResult(
        success=passed,
        output_path=str(final_destination),
        passes=len(history),
        initial_score=initial_score,
        final_score=best_score,
        report=best_report,
        history=history,
        reason=(
            "Reached the acceptance threshold."
            if passed
            else f"Best score {best_score:.3f} after {len(history)} pass(es) is still below {cfg.threshold:.2f}."
        ),
    )


def _decode(path: Path):
    """Decode an image to a BGR array, returning (array, None) or (None, error)."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return image, None
