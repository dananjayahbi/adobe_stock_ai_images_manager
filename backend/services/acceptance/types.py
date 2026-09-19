"""Shared types and issue codes for acceptance scoring.

Every issue code emitted by the scorer maps to exactly one corrective action in
``services.refine.recipe``. Keeping the vocabulary in one place means the
refiner can never silently ignore a problem the scorer reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Issue vocabulary
# --------------------------------------------------------------------------- #

# Technical / container level
WRONG_FORMAT = "wrong_format"
NOT_SRGB = "not_srgb"
LOW_RESOLUTION = "low_resolution"
EXCESSIVE_RESOLUTION = "excessive_resolution"
FILE_TOO_LARGE = "file_too_large"

# Tone
HIGHLIGHTS_CLIPPED = "highlights_clipped"
SHADOWS_CRUSHED = "shadows_crushed"

# Colour
OVERALL_OVERSATURATED = "overall_oversaturated"
SKIN_TONE_CAST = "skin_tone_cast"
NEON_GREENS = "neon_greens"

# Detail / upscaler artefacts
EDGE_HALO = "edge_halo"
CHROMA_FRINGE = "chroma_fringe"
SOFT_FOCUS = "soft_focus"

# Texture / synthetic tells
FLAT_SYNTHETIC_TEXTURE = "flat_synthetic_texture"
EXCESSIVE_NOISE = "excessive_noise"

# Semantic (LLM) findings
SEMANTIC_FLAGGED = "semantic_flagged"
HALLUCINATED_TEXT = "hallucinated_text"
POSSIBLE_IP = "possible_ip"

ISSUE_CODES: tuple[str, ...] = (
    WRONG_FORMAT,
    NOT_SRGB,
    LOW_RESOLUTION,
    EXCESSIVE_RESOLUTION,
    FILE_TOO_LARGE,
    HIGHLIGHTS_CLIPPED,
    SHADOWS_CRUSHED,
    OVERALL_OVERSATURATED,
    SKIN_TONE_CAST,
    NEON_GREENS,
    EDGE_HALO,
    CHROMA_FRINGE,
    SOFT_FOCUS,
    FLAT_SYNTHETIC_TEXTURE,
    EXCESSIVE_NOISE,
    SEMANTIC_FLAGGED,
    HALLUCINATED_TEXT,
    POSSIBLE_IP,
)

#: Issue codes the pixel-level refiner is able to remediate automatically.
REFINABLE_CODES: frozenset[str] = frozenset(
    {
        HIGHLIGHTS_CLIPPED,
        SHADOWS_CRUSHED,
        OVERALL_OVERSATURATED,
        SKIN_TONE_CAST,
        NEON_GREENS,
        EDGE_HALO,
        CHROMA_FRINGE,
        SOFT_FOCUS,
        FLAT_SYNTHETIC_TEXTURE,
        EXCESSIVE_NOISE,
    }
)

#: Issue codes fixed at the *container* level rather than by editing pixels.
#:
#: The colour profile is a property of the encoding, not of the pixel values, so
#: the pixel recipe cannot address it - but it is still fully automatic (see
#: :mod:`services.autofix.colour`). Keeping it in ``MANUAL_ONLY_CODES`` was wrong:
#: it told the operator to fix by hand something the pipeline can do itself.
CONTAINER_FIXABLE_CODES: frozenset[str] = frozenset({NOT_SRGB})

#: Everything the auto-fix engine can correct without human input.
AUTOFIXABLE_CODES: frozenset[str] = REFINABLE_CODES | CONTAINER_FIXABLE_CODES

#: Issue codes that require a human decision and can never be auto-fixed.
MANUAL_ONLY_CODES: frozenset[str] = frozenset(
    {
        WRONG_FORMAT,
        LOW_RESOLUTION,
        EXCESSIVE_RESOLUTION,
        FILE_TOO_LARGE,
        SEMANTIC_FLAGGED,
        HALLUCINATED_TEXT,
        POSSIBLE_IP,
    }
)

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


@dataclass(frozen=True)
class Issue:
    """A single compliance problem detected in an image."""

    code: str
    severity: str  # "critical" | "major" | "minor"
    detail: str
    #: Measured value that triggered the issue, when applicable.
    value: float | None = None

    @property
    def refinable(self) -> bool:
        """True when this issue can be corrected without human input.

        Reports the *engine's* capability, which is what the UI's "auto-fixable"
        badge promises - it therefore includes container-level fixes such as the
        sRGB profile, not just pixel-recipe corrections.
        """
        return self.code in AUTOFIXABLE_CODES

    @property
    def pixel_refinable(self) -> bool:
        """True only when the Stage 4 pixel recipe has a branch for this code."""
        return self.code in REFINABLE_CODES

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
            "value": self.value,
            "refinable": self.refinable,
        }


@dataclass
class SubScore:
    """One weighted component of the overall acceptance score."""

    key: str
    label: str
    score: float  # 0..1
    weight: float
    issues: list[Issue] = field(default_factory=list)
    #: The individual measurements that were averaged into ``score``.
    #: Kept so the overall ceiling can react to a single failing criterion
    #: instead of only the group average that hid it.
    components: list[float] = field(default_factory=list)

    @property
    def worst_component(self) -> float:
        """Lowest individual measurement, falling back to the group score."""
        return min(self.components) if self.components else self.score

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "score": round(self.score, 4),
            "weight": round(self.weight, 4),
            "components": [round(value, 4) for value in self.components],
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass
class AcceptanceReport:
    """Aggregate acceptance verdict for a single image."""

    score: float
    threshold: float
    passed: bool
    sub_scores: dict[str, SubScore]
    issues: list[Issue]
    metrics: dict[str, float]
    #: True when an LLM semantic score contributed to the total.
    semantic_included: bool = False

    @property
    def refinable_issues(self) -> list[Issue]:
        """Issues the Stage 4 pixel recipe has a branch for.

        Deliberately narrower than :attr:`Issue.refinable`: the recipe cannot
        act on the colour profile, so offering it those issues would make
        ``apply_recipe`` report them as unaddressable and stall the pass loop.
        """
        return [issue for issue in self.issues if issue.pixel_refinable]

    @property
    def blocking_issues(self) -> list[Issue]:
        """Issues the pipeline cannot resolve without a human decision."""
        return [issue for issue in self.issues if not issue.refinable]

    @property
    def confidence_percent(self) -> float:
        return round(self.score * 100, 2)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "confidence_percent": self.confidence_percent,
            "threshold": self.threshold,
            "passed": self.passed,
            "semantic_included": self.semantic_included,
            "sub_scores": {
                key: value.to_dict() for key, value in self.sub_scores.items()
            },
            "issues": [issue.to_dict() for issue in self.issues],
            "refinable_codes": sorted(
                {issue.code for issue in self.refinable_issues}
            ),
            "blocking_codes": sorted(
                {issue.code for issue in self.blocking_issues}
            ),
            "metrics": {key: round(value, 4) for key, value in self.metrics.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AcceptanceReport":
        """Rebuild a report from its serialized form (used for stored records)."""
        sub_scores = {
            key: SubScore(
                key=value["key"],
                label=value["label"],
                score=value["score"],
                weight=value["weight"],
                issues=[
                    Issue(
                        code=item["code"],
                        severity=item["severity"],
                        detail=item["detail"],
                        value=item.get("value"),
                    )
                    for item in value.get("issues", [])
                ],
                components=[float(c) for c in value.get("components", [])],
            )
            for key, value in (data.get("sub_scores") or {}).items()
        }

        return cls(
            score=float(data.get("score", 0.0)),
            threshold=float(data.get("threshold", 0.0)),
            passed=bool(data.get("passed", False)),
            sub_scores=sub_scores,
            issues=[
                Issue(
                    code=item["code"],
                    severity=item["severity"],
                    detail=item["detail"],
                    value=item.get("value"),
                )
                for item in data.get("issues", [])
            ],
            metrics={k: float(v) for k, v in (data.get("metrics") or {}).items()},
            semantic_included=bool(data.get("semantic_included", False)),
        )
