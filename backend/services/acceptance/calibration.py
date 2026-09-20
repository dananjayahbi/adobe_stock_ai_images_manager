"""Evidence-based calibration record for the acceptance scorer.

Every threshold the scorer applies is either (a) published by Adobe, or (b) an
internal heuristic. This module makes that distinction explicit and records the
source, so a future change can tell a *requirement* from a *guess*.

Research date: 2026-09-20. Primary sources are Adobe's contributor help pages;
contributor anecdotes are labelled as such and are never used to set a
requirement.

Key finding driving the recalibration: Adobe's published quality criteria for
photos are **over/underexposure, soft focus, poor white balance, heavy editing /
over-sharpening, dust spots, and over/undersaturation** - and noise is something
to be *minimised*. Nothing in Adobe's guidance makes a clean, low-noise image a
defect, yet the scorer used to penalise exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Source URLs
# --------------------------------------------------------------------------- #

ADOBE_PHOTO_TECHNICAL = (
    "https://helpx.adobe.com/stock/contributor/submit-your-content/submit-photos/"
    "technical-legal-requirements-photo-submission.html"
)
ADOBE_QUALITY_TECHNICAL = (
    "https://helpx.adobe.com/stock/contributor/content-moderation/"
    "quality-technical-standards-reasons-content-refusal.html"
)
ADOBE_COMMON_REFUSAL = (
    "https://helpx.adobe.com/stock/contributor/content-moderation/"
    "common-reasons-content-refusal.html"
)
ADOBE_AI_GUIDELINES = (
    "https://helpx.adobe.com/stock/contributor/submit-your-content/"
    "submit-generative-ai-content/generative-ai-content-guidelines.html"
)
ADOBE_AI_PHOTO = (
    "https://helpx.adobe.com/stock/contributor/submit-your-content/"
    "submit-generative-ai-content/generative-ai-photo-submission-guidelines.html"
)
ADOBE_PHOTO_EDITING = (
    "https://helpx.adobe.com/stock/contributor/submit-your-content/submit-photos/"
    "photo-editing-best-practices.html"
)

# --------------------------------------------------------------------------- #
# Defect tiers
# --------------------------------------------------------------------------- #

#: A defect Adobe states as a refusal reason, and which reviewers lead with.
#: A failure here may cap the overall score - Adobe refuses on any single
#: failed criterion.
TIER_DECISIVE = "decisive"

#: A real but secondary signal. It must move the score, but it must NEVER cap
#: it: community evidence shows reviewers reject on one criterion at a time
#: ("the review ends at problem #1"), and treating a nitpick as decisive is what
#: pinned otherwise-fine images at the ceiling floor.
TIER_ADVISORY = "advisory"


@dataclass(frozen=True)
class Threshold:
    """One tunable value plus where it came from."""

    key: str
    value: float
    unit: str
    source: str
    #: "adobe" = published requirement; "internal" = our own heuristic.
    provenance: str
    note: str = ""

    @property
    def is_requirement(self) -> bool:
        return self.provenance == "adobe"


#: The thresholds the scorer applies, with provenance. Container-level values
#: are Adobe requirements; every pixel-level value is an internal heuristic,
#: because Adobe publishes none.
THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(
        "min_megapixels", 4.0, "MP", ADOBE_PHOTO_TECHNICAL, "adobe",
        "Adobe: photos must be 4-100 MP.",
    ),
    Threshold(
        "max_megapixels", 100.0, "MP", ADOBE_PHOTO_TECHNICAL, "adobe",
        "Adobe's stated upper bound. Do NOT lower to 8 MP: that figure is a "
        "stale 2023 note for generative AI, contradicted by Adobe's own range.",
    ),
    Threshold(
        "max_file_size_mb", 45.0, "MB", ADOBE_PHOTO_TECHNICAL, "adobe",
        "Adobe's stated cap for photos.",
    ),
    Threshold(
        "sharpness_ideal", 120.0, "laplacian var", ADOBE_QUALITY_TECHNICAL,
        "internal",
        "Adobe publishes NO sharpness number; it says 'check at 100% zoom'. "
        "This equals MIN_LAPLACIAN_VARIANCE, the app's established pass line.",
    ),
    Threshold(
        "chroma_misalignment_fail", 0.60, "0-2 index", ADOBE_QUALITY_TECHNICAL,
        "internal",
        "Adobe lists 'colour fringing: remove chromatic aberration' as general "
        "editing hygiene, NOT as an AI-specific defect, and community evidence "
        "ranks it minor. Calibrated against synthetic ground truth: clean "
        "frames measure <=0.27, visible CA >=0.79.",
    ),
    Threshold(
        "noise_flat_fail", 25.0, "sigma", ADOBE_QUALITY_TECHNICAL, "internal",
        "Adobe: 'check that noise and artifacts are minimized' but publishes no "
        "number. Measured over the flattest 30% of the frame (where noise is "
        "visible) against synthetic ground truth: clean 0.0, lightly grained "
        "~2, visibly noisy >=20. A whole-frame sigma would count foliage "
        "texture as noise.",
    ),
)


def threshold(key: str) -> Threshold:
    """Look up a recorded threshold by key."""
    for item in THRESHOLDS:
        if item.key == key:
            return item
    raise KeyError(f"No recorded threshold named {key!r}")


# --------------------------------------------------------------------------- #
# Issue tiers
# --------------------------------------------------------------------------- #

#: Codes that may cap the score.
DECISIVE_CODES: frozenset[str] = frozenset(
    {
        "wrong_format",
        "not_srgb",
        "low_resolution",
        "excessive_resolution",
        "file_too_large",
        "highlights_clipped",
        "shadows_crushed",
        "soft_focus",
        "edge_halo",
        "excessive_noise",
        "overall_oversaturated",
        "skin_tone_cast",
        "neon_greens",
        "semantic_flagged",
        "hallucinated_text",
        "possible_ip",
    }
)

#: Codes that adjust the score but can never cap it.
ADVISORY_CODES: frozenset[str] = frozenset(
    {
        "chroma_fringe",
        "flat_synthetic_texture",
    }
)


def tier_for(code: str) -> str:
    """Return the tier of ``code`` (defaults to decisive for safety)."""
    return TIER_ADVISORY if code in ADVISORY_CODES else TIER_DECISIVE


# --------------------------------------------------------------------------- #
# Evidence that overturned the old behaviour
# --------------------------------------------------------------------------- #

#: Statements the previous calibration assumed, which the research did NOT
#: support. Recorded so the same mistakes are not reintroduced.
REFUTED_ASSUMPTIONS: tuple[tuple[str, str], ...] = (
    (
        "A clean image with no sensor noise is suspicious.",
        "REFUTED. Adobe: 'check that noise and artifacts are MINIMIZED'. No "
        "source shows a refusal for cleanliness. The real 'waxy' signal is loss "
        "of local skin/object texture from over-denoising, not a missing noise "
        "floor.",
    ),
    (
        "Adding synthetic grain helps pass Adobe review.",
        "REFUTED. Adobe wants 'clean images with no added grain, filters or "
        "textures'; its photo-editing Don'ts forbid adding non-natural elements.",
    ),
    (
        "Chromatic aberration is a primary AI-image defect.",
        "REFUTED. Adobe mentions it once as general editing hygiene. Community "
        "experts diagnose anatomy, focus and exposure instead.",
    ),
    (
        "AI photos must be 16-24 MP.",
        "NO EVIDENCE. Only upscaler vendor blogs claim this. Adobe's range is "
        "4-100 MP.",
    ),
    (
        "Upscaling is a rejection reason for photos.",
        "REFUTED. Adobe rejects upscaled VIDEO and has no equivalent photo rule; "
        "only upscaling ARTEFACTS are refused.",
    ),
    (
        "A numeric quality threshold can predict Adobe's verdict.",
        "REFUTED. Reviewers check one box only, assets go to reviewers of "
        "varying experience, and 37 rejected files were later accepted "
        "unchanged. The score is a ranking signal, not a verdict.",
    ),
)
