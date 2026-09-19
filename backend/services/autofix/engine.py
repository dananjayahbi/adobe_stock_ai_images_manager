"""The auto-fix engine.

Stage 5 tells the operator *what* is wrong with an image. Until now it could not
tell them to *do* anything about it: the report flagged issues as
"auto-fixable" while the only button available was a full Stage 4 re-run that
re-derived its own recipe and gave no explanation of what changed.

This module closes that gap. It takes the issues the operator is actually
looking at, applies the corrections that genuinely address them, and re-scores
so the operator sees the new verdict rather than a promise.

Two kinds of correction exist and both are handled here:

* **Container** - the sRGB colour profile. A wrong profile changes how every
  pixel is interpreted, so it is fixed by transforming or re-tagging the file
  (:mod:`services.autofix.container`) rather than by editing pixels.
* **Pixel** - tone, colour, edge and texture problems, delegated to the existing
  Stage 4 recipe (:func:`services.refine.recipe.apply_recipe`) so the two paths
  can never disagree about what a correction should be.

Corrections that need a human decision - a suspected logo, a model release, a
resolution ceiling - are reported as ``manual`` and never silently attempted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings, settings as default_settings
from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import AcceptanceReport
from services.autofix.container import apply_container_fixes
from services.refine.recipe import apply_recipe
from services.srgb_profile import has_srgb_profile, write_srgb_jpeg

logger = logging.getLogger(__name__)

#: Passes attempted before giving up. Mirrors the Stage 4 budget: each pass is
#: measured independently, so a correction that helps one metric can hurt
#: another and more passes are not automatically better.
DEFAULT_MAX_PASSES = 3


@dataclass
class AutoFixResult:
    """Outcome of an auto-fix attempt on one image."""

    success: bool
    #: Path of the corrected file, when one was written.
    output_path: str | None = None
    passes: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    initial_passed: bool = False
    final_passed: bool = False
    #: Issue codes the engine successfully addressed.
    fixed: list[str] = field(default_factory=list)
    #: Issue codes that remain and are still auto-fixable (retry may help).
    remaining_fixable: list[str] = field(default_factory=list)
    #: Issue codes that need a human decision.
    manual: list[str] = field(default_factory=list)
    #: Per-pass narrative: what was changed and what it scored.
    history: list[dict] = field(default_factory=list)
    #: True when the written file verifiably carries an sRGB profile.
    srgb_embedded: bool = False
    reason: str = ""
    #: The final report, so the caller can persist it without re-scoring.
    report: AcceptanceReport | None = None

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
            "initial_passed": self.initial_passed,
            "final_passed": self.final_passed,
            "fixed": self.fixed,
            "remaining_fixable": self.remaining_fixable,
            "manual": self.manual,
            "history": self.history,
            "srgb_embedded": self.srgb_embedded,
            "reason": self.reason,
            "report": self.report.to_dict() if self.report else None,
        }


def _codes(issues) -> list[str]:
    """De-duplicated issue codes, order preserved."""
    return list(dict.fromkeys(issue.code for issue in issues))


#: Severity ranking, worst first. Mirrors the scorer's own ordering.
_SEVERITY_RANK = {"critical": 0, "major": 1, "minor": 2}


def _worst_severity(issues) -> dict[str, int]:
    """Worst (lowest) severity rank per issue code."""
    ranks: dict[str, int] = {}
    for issue in issues:
        rank = _SEVERITY_RANK.get(issue.severity, 3)
        if issue.code not in ranks or rank < ranks[issue.code]:
            ranks[issue.code] = rank
    return ranks


def _classify(
    attempted: set[str], before, after
) -> tuple[list[str], list[str]]:
    """Split attempted codes into genuinely-fixed and still-outstanding.

    Success is judged by whether the *measurement* moved, not by whether the
    recipe ran. Corrections are capped at a conservative strength to respect
    Adobe's "no overprocessing" guidance, so a badly out-of-tolerance metric can
    legitimately improve without clearing its threshold. Reporting such a code as
    fixed would be a lie; reporting it as untouched would be equally wrong, so a
    strict severity reduction counts as fixed.
    """
    before_rank = _worst_severity(before)
    after_rank = _worst_severity(after)

    fixed = [
        code
        for code in attempted
        if code not in after_rank or after_rank[code] > before_rank.get(code, 3)
    ]
    return sorted(fixed), sorted(after_rank)


def _is_fixable_code(report, code: str) -> bool:
    """True when ``code`` is still fixable, so a retry could help."""
    return any(issue.code == code and issue.refinable for issue in report.issues)


def auto_fix_image(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    semantic: dict | None = None,
    settings: Settings | None = None,
    config: AcceptanceConfig | None = None,
    max_passes: int = DEFAULT_MAX_PASSES,
) -> AutoFixResult:
    """Fix everything automatically fixable, then re-score.

    Args:
        file_path: The image to correct (never modified in place).
        output_dir: Directory receiving the corrected copy.
        record_id: Names the output deterministically, as Stage 4 does.
        semantic: Optional LLM audit dict, carried into every re-score so a
            semantic regression is caught as quickly as a pixel one.
        settings: Application settings override.
        config: Acceptance thresholds override.
        max_passes: Upper bound on correction passes.

    Returns:
        An :class:`AutoFixResult`. ``success`` means a corrected file was
        written - **not** that the image now passes. An image whose only
        remaining problem is a suspected logo is a legitimate result: the fix
        ran, and the manual issue is reported as such.
    """
    cfg_settings = settings or default_settings
    cfg = config or AcceptanceConfig.from_settings()
    quality = int(getattr(cfg_settings, "EXPORT_JPEG_QUALITY", 95))

    source = Path(file_path)
    if not source.exists():
        return AutoFixResult(False, reason=f"File not found: {file_path}")

    report = score_image(source, config=cfg, semantic=semantic)
    initial_score = report.score
    initial_passed = report.passed
    initial_issues = list(report.issues)

    result = AutoFixResult(
        success=False,
        initial_score=initial_score,
        final_score=initial_score,
        initial_passed=initial_passed,
        final_passed=initial_passed,
    )

    if report.passed:
        result.reason = "Already clears the acceptance threshold; nothing to fix."
        result.manual = _codes(report.issues)
        result.report = report
        return result

    # Container fixes run first: the colour profile determines how the pixel
    # corrections are interpreted, so converting afterwards would apply them in
    # the wrong space.
    container = apply_container_fixes(source, report.issues)
    if container.image_bgr is None:
        result.reason = "Could not decode the image."
        return result

    working = container.image_bgr
    # Codes the engine *attempted*. Whether each attempt actually worked is
    # decided by the final report, not by the recipe's own claim - a correction
    # can be applied and still leave the measurement outside tolerance.
    attempted: set[str] = set(container.addressed)
    if container.notes:
        result.history.append(
            {"pass": 0, "score": round(initial_score, 4), "notes": container.notes}
        )

    destination = Path(output_dir) / f"{record_id}-refined.jpg"

    for pass_number in range(1, max(1, max_passes) + 1):
        fixable = report.refinable_issues
        if not fixable:
            break
        outcome = apply_recipe(working, fixable, metrics=report.metrics)
        if not outcome.changed:
            result.history.append(
                {
                    "pass": pass_number,
                    "score": round(report.score, 4),
                    "note": "No further automatic correction was available.",
                }
            )
            break

        working = outcome.image
        attempted.update(outcome.addressed)

        # Score the file that will actually be delivered, not the in-memory
        # array, so the number the operator sees matches the bytes on disk.
        if not write_srgb_jpeg(working, destination, quality):
            result.reason = "Failed to write the corrected image."
            return result

        report = score_image(destination, config=cfg, semantic=semantic)
        result.history.append(
            {
                "pass": pass_number,
                "score": round(report.score, 4),
                "operations": [step.to_dict() for step in outcome.steps],
            }
        )
        result.passes = pass_number

        if report.passed:
            break

    if result.passes == 0:
        # Nothing pixel-level was applicable; still deliver the container fix so
        # the operator is not told "fixed" with no file behind it.
        if not write_srgb_jpeg(working, destination, quality):
            result.reason = "Failed to write the corrected image."
            return result
        report = score_image(destination, config=cfg, semantic=semantic)

    result.success = True
    result.output_path = str(destination)
    result.final_score = report.score
    result.final_passed = report.passed
    result.report = report

    # Classify against the *final* report rather than the recipe's claims: a
    # correction can be applied and still leave the metric outside tolerance, so
    # the outcome is judged on the measurements, not on the work done.
    fixed, outstanding = _classify(attempted, initial_issues, report.issues)
    result.fixed = fixed
    # Exclude anything already reported as fixed: a code appearing in both lists
    # would read as "resolved" and "still a problem" at once.
    fixed_set = set(fixed)
    result.remaining_fixable = sorted(
        code
        for code in outstanding
        if code not in fixed_set and _is_fixable_code(report, code)
    )
    result.manual = _codes(report.blocking_issues)
    # Read the profile back rather than assuming the writer embedded it: the
    # same mistake made the Stage 3 report claim sRGB on an untagged file.
    result.srgb_embedded = has_srgb_profile(destination)
    result.reason = (
        f"{initial_score:.1%} → {report.score:.1%} after {result.passes} pass(es)."
    )
    return result
