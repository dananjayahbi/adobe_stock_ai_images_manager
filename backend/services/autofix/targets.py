"""Targets for the adaptive auto-fix.

The single-shot auto-fix stops as soon as it has run the recipe once, which is
why it could report "fixed 4 issues" while the score stayed flat. The adaptive
mode instead drives the image toward a *goal*, and this module defines what that
goal means.

The goal is deliberately expressed per-dimension rather than as one overall
number. The acceptance score is capped by its worst dimension
(``ceiling_floor + ceiling_span * worst_component``), so an image whose
technical dimension sits at 0.40 can never score above 73% no matter how many
pixel corrections succeed. Raising every auto-fixable dimension past the target
is therefore the only way to make the overall number move - and it also gives
the operator a far more actionable readout than a single percentage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.acceptance.types import AUTOFIXABLE_CODES

#: Adobe's own acceptance bar, and the default target for the adaptive loop.
DEFAULT_TARGET = 0.80

#: The lowest target worth offering. Below this the "fix" would be cosmetic:
#: it would report success while leaving an image Adobe would still refuse.
MIN_TARGET = 0.60

#: Highest target. 1.0 is unreachable in practice (it demands a flawless frame),
#: so the UI caps here to keep the loop from grinding to no purpose.
MAX_TARGET = 0.95


def clamp_target(value: float | None) -> float:
    """Coerce a requested target into the supported range."""
    if value is None:
        return DEFAULT_TARGET
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TARGET
    return float(min(max(numeric, MIN_TARGET), MAX_TARGET))


@dataclass
class DimensionTarget:
    """One score component the adaptive loop tries to lift."""

    key: str
    label: str
    score: float
    weight: float
    #: Issue codes inside this dimension the engine can actually correct.
    fixable_codes: list[str] = field(default_factory=list)
    #: Issue codes inside this dimension that need a human.
    manual_codes: list[str] = field(default_factory=list)

    @property
    def is_fixable(self) -> bool:
        """True when correcting something here could raise the score."""
        return bool(self.fixable_codes)

    def met(self, target: float) -> bool:
        return self.score >= target

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 4),
            "weight": round(self.weight, 4),
            "fixable_codes": self.fixable_codes,
            "manual_codes": self.manual_codes,
            "is_fixable": self.is_fixable,
        }


def _fixable_and_manual(sub_score) -> tuple[list[str], list[str]]:
    """Split a sub-score's issue codes by whether the engine can correct them."""
    fixable: list[str] = []
    manual: list[str] = []
    for issue in sub_score.issues:
        bucket = fixable if issue.code in AUTOFIXABLE_CODES else manual
        if issue.code not in bucket:
            bucket.append(issue.code)
    return sorted(fixable), sorted(manual)


def dimensions_from_report(report) -> list[DimensionTarget]:
    """Build the per-dimension goal list from an acceptance report."""
    dimensions: list[DimensionTarget] = []
    for key, sub in report.sub_scores.items():
        fixable, manual = _fixable_and_manual(sub)
        dimensions.append(
            DimensionTarget(
                key=key,
                label=sub.label,
                # The *worst component* is what caps the overall score, so it is
                # the honest number to show and to test against the target.
                score=sub.worst_component,
                weight=sub.weight,
                fixable_codes=fixable,
                manual_codes=manual,
            )
        )
    return dimensions


def diagnose_stuck(dimension: DimensionTarget) -> str:
    """Explain why a dimension cannot reach the target.

    This exists because of a measured, non-obvious property of the scorer: a
    component's score is ``1 - ramp(value, tolerance, fail)``, which collapses to
    **exactly 0.0** as soon as ``value >= fail``. A correction that improves the
    measurement without crossing back under ``fail`` therefore earns no credit at
    all - the score does not budge, and without an explanation the operator is
    left assuming the fix silently failed.

    Real example from this pipeline: a chroma-fringe ratio of 0.344 against
    ``fringe_fail = 0.15``. Even the strongest defringe pass only reaches ~0.19,
    still above the threshold, so the dimension stays pinned at 0.0.
    """
    if dimension.is_fixable:
        return (
            f"{dimension.label} is at {dimension.score * 100:.0f}% and its "
            f"corrections ({', '.join(dimension.fixable_codes)}) did not move the "
            "measurement past the scorer's threshold. The score for a dimension is "
            "all-or-nothing below its tolerance, so a partial improvement earns no "
            "credit. Fixing this needs a stronger correction than the pipeline can "
            "safely apply, or a re-shoot / re-upscale."
        )
    return (
        f"{dimension.label} is at {dimension.score * 100:.0f}% and is not "
        "correctable by the pipeline - it needs a manual decision."
    )


@dataclass
class TargetProgress:
    """How close the image is to the operator's goal."""

    target: float
    overall_score: float
    dimensions: list[DimensionTarget]

    @property
    def unmet_fixable(self) -> list[DimensionTarget]:
        """Dimensions below target that the engine could still improve."""
        return [d for d in self.dimensions if d.is_fixable and not d.met(self.target)]

    @property
    def unmet_manual(self) -> list[DimensionTarget]:
        """Dimensions below target that only a human can fix."""
        return [d for d in self.dimensions if not d.is_fixable and not d.met(self.target)]

    @property
    def all_met(self) -> bool:
        return not self.unmet_fixable and not self.unmet_manual

    @property
    def blocked_by_manual(self) -> bool:
        """True when nothing auto-fixable remains but the goal is unmet."""
        return not self.unmet_fixable and bool(self.unmet_manual)

    def to_dict(self) -> dict:
        return {
            "target": round(self.target, 4),
            "overall_score": round(self.overall_score, 4),
            "all_met": self.all_met,
            "blocked_by_manual": self.blocked_by_manual,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "unmet_fixable": [d.key for d in self.unmet_fixable],
            "unmet_manual": [d.key for d in self.unmet_manual],
        }
