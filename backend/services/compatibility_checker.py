"""Stage 5 - the overall compatibility gate.

Stage 4 already nudged the image toward compliance; this stage answers the
operator's actual question: *does this image clear Adobe's bar, and if not,
exactly what still stands in the way?*

It runs the same acceptance scorer as Stage 4 but with the semantic audit
attached, so the verdict combines pixel evidence with the model's read on
anatomy, artefacts, and IP risk. The result is persisted as the record's
``acceptance_report`` and drives the PASSED/FLAGGED status.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import AcceptanceReport

logger = logging.getLogger(__name__)

#: Human-readable remediation advice keyed by issue code, shown in the UI when
#: an image fails so the operator is not left guessing what to do next.
REMEDIATION_HINTS: dict[str, str] = {
    "wrong_format": "Re-export the file as JPEG; Adobe Stock rejects PNG and TIFF for photos.",
    "not_srgb": "Convert the colour profile to sRGB IEC61966-2.1 before exporting.",
    "low_resolution": "Upscale to at least 4 MP (Stage 3) before resubmitting.",
    "excessive_resolution": "Downscale below 100 MP to stay inside Adobe's resolution ceiling.",
    "file_too_large": "Lower the export quality or resolution; the cap is 45 MB per file.",
    "highlights_clipped": "Pull the white point down (e.g. 252) so blown areas retain detail.",
    "shadows_crushed": "Raise the black point (e.g. 4) so deep shadows are not pure black.",
    "overall_oversaturated": "Reduce global saturation by 5-10% to a natural range.",
    "skin_tone_cast": "Desaturate the red/orange band to remove the AI skin cast.",
    "neon_greens": "Desaturate the yellow/green band; foliage is reading as radioactive.",
    "edge_halo": "Defringe or apply a 1px edge-restricted blur to kill the sharpening halo.",
    "chroma_fringe": "Remove purple/green colour aberration along high-contrast edges.",
    "soft_focus": "Apply a restrained unsharp mask; the image reads as soft at 100% zoom.",
    "flat_synthetic_texture": "Add 0.6-1.2% monochromatic sensor grain to break up waxy surfaces.",
    "excessive_noise": "Apply light denoising; the grain profile is above a natural sensor floor.",
    "semantic_flagged": "Inspect the flagged area at 100% zoom and repair the artefact by hand.",
    "hallucinated_text": "Erase background signage and gibberish lettering before resubmitting.",
    "possible_ip": "Remove or repaint the suspected logo, badge, or brand motif.",
}


@dataclass
class CompatibilityResult:
    """Verdict from the Stage 5 gate."""

    passed: bool
    report: AcceptanceReport
    #: Ordered, operator-facing advice for every blocking issue.
    remediation: list[str]
    summary: str

    @property
    def score(self) -> float:
        return self.report.score

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": round(self.report.score, 4),
            "confidence_percent": self.report.confidence_percent,
            "threshold": self.report.threshold,
            "summary": self.summary,
            "remediation": self.remediation,
            "report": self.report.to_dict(),
        }


def _build_remediation(report: AcceptanceReport) -> list[str]:
    """Turn blocking issues into ordered, de-duplicated operator advice."""
    hints: list[str] = []
    seen: set[str] = set()

    # Critical issues first so the most serious problem reads first.
    ordered = sorted(
        report.issues,
        key=lambda issue: {"critical": 0, "major": 1, "minor": 2}.get(issue.severity, 3),
    )
    for issue in ordered:
        if issue.code in seen:
            continue
        seen.add(issue.code)
        hint = REMEDIATION_HINTS.get(issue.code)
        if hint:
            hints.append(f"{issue.detail} → {hint}")
        else:
            hints.append(issue.detail)

    return hints


def check_compatibility(
    file_path: str | Path,
    *,
    semantic: dict | None = None,
    config: AcceptanceConfig | None = None,
) -> CompatibilityResult:
    """Run the full acceptance algorithm and gate at the configured threshold.

    Args:
        file_path: The current working image (refined copy when available).
        semantic: Optional LLM audit dict contributing the semantic sub-score.
        config: Acceptance thresholds override.

    Returns:
        A :class:`CompatibilityResult` carrying the report, a pass/fail verdict,
        and concrete remediation steps for anything still blocking.
    """
    cfg = config or AcceptanceConfig.from_settings()
    report = score_image(file_path, config=cfg, semantic=semantic)
    remediation = _build_remediation(report) if not report.passed else []

    if report.passed:
        summary = (
            f"Compatible - acceptance score {report.confidence_percent:.1f}% "
            f"clears the {report.threshold * 100:.0f}% threshold."
        )
    else:
        blockers = sorted({issue.code for issue in report.blocking_issues})
        summary = (
            f"Below threshold - score {report.confidence_percent:.1f}% "
            f"(needs {report.threshold * 100:.0f}%). "
            f"{len(report.issues)} issue(s) detected"
            + (f", {len(blockers)} requiring manual attention." if blockers else ".")
        )

    return CompatibilityResult(
        passed=report.passed,
        report=report,
        remediation=remediation,
        summary=summary,
    )
