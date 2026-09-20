"""Aggregate pixel measurements into a single acceptance score.

The score is a weighted mean of five deterministic sub-scores plus an optional
LLM semantic sub-score. Weights are renormalized when the semantic component is
unavailable, so a missing LLM reply degrades gracefully instead of capping the
maximum achievable score.

Thresholds and weights come from :class:`AcceptanceConfig`, which reads the
application settings so the operator can tune them without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from config import settings
from services.acceptance import pixel_metrics
from services.acceptance.types import (
    CHROMA_FRINGE,
    EDGE_HALO,
    EXCESSIVE_NOISE,
    EXCESSIVE_RESOLUTION,
    FILE_TOO_LARGE,
    FLAT_SYNTHETIC_TEXTURE,
    HALLUCINATED_TEXT,
    HIGHLIGHTS_CLIPPED,
    LOW_RESOLUTION,
    NEON_GREENS,
    NOT_SRGB,
    OVERALL_OVERSATURATED,
    POSSIBLE_IP,
    SEMANTIC_FLAGGED,
    SHADOWS_CRUSHED,
    SKIN_TONE_CAST,
    SOFT_FOCUS,
    WRONG_FORMAT,
    AcceptanceReport,
    Issue,
    SubScore,
)

logger = logging.getLogger(__name__)

#: Sub-score keys in report order.
SUB_SCORE_KEYS = ("technical", "exposure", "color", "detail", "texture", "semantic")

SUB_SCORE_LABELS = {
    "technical": "Technical & Format",
    "exposure": "Exposure & Dynamic Range",
    "color": "Colour Balance",
    "detail": "Sharpness & Edge Integrity",
    "texture": "Sensor Texture Realism",
    "semantic": "Semantic Quality (AI Review)",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _ramp(value: float, bad: float, good: float) -> float:
    """Linear 0..1 score: ``bad`` -> 0.0, ``good`` -> 1.0 (either direction)."""
    if bad == good:
        return 1.0
    return _clamp((value - bad) / (good - bad))


@dataclass(frozen=True)
class AcceptanceConfig:
    """Tunable thresholds for acceptance scoring."""

    # Overall gate
    threshold: float = 0.80

    # Weights (sum to 1.0 before semantic renormalization)
    weight_technical: float = 0.30
    weight_exposure: float = 0.20
    weight_color: float = 0.15
    weight_detail: float = 0.15
    weight_texture: float = 0.10
    weight_semantic: float = 0.10

    # Resolution / size
    min_megapixels: float = 4.0
    max_megapixels: float = 100.0
    max_file_size_mb: float = 45.0

    # Clipping tolerances (share of pixels allowed to clip before penalty)
    highlight_tolerance: float = 0.010
    highlight_fail: float = 0.060
    shadow_tolerance: float = 0.020
    shadow_fail: float = 0.080

    # Saturation band (ideal overall saturation window)
    sat_ideal_low: float = 0.20
    sat_ideal_high: float = 0.45
    sat_fail_low: float = 0.06
    sat_fail_high: float = 0.72
    skin_sat_ideal: float = 0.42
    skin_sat_fail: float = 0.68
    green_sat_ideal: float = 0.50
    green_sat_fail: float = 0.80

    # Sharpness (Laplacian variance). ``sharpness_ideal`` is the point at which
    # this dimension scores a full 1.0, and it is deliberately set to the app's
    # established pass line (MIN_LAPLACIAN_VARIANCE) rather than an aspirational
    # target - otherwise a compliant image would be flagged as soft and capped
    # by the worst-dimension ceiling.
    sharpness_fail: float = 60.0
    sharpness_ideal: float = 120.0

    # Edge artefacts (share of edge pixels affected)
    halo_tolerance: float = 0.05
    halo_fail: float = 0.30
    #: Chromatic aberration is measured as channel MISALIGNMENT (0..2), not as
    #: a share of edge pixels. Adobe lists "colour fringing" once, as general
    #: editing hygiene, and never as an AI-specific defect; community evidence
    #: ranks it a minor nitpick. Calibrated against synthetic ground truth:
    #: clean frames measure <= 0.27, clearly visible CA >= 0.79.
    chroma_misalignment_tolerance: float = 0.20
    chroma_misalignment_fail: float = 0.60

    # Texture. Adobe's rule is "check that noise and artifacts are minimized" -
    # there is no published number, and the objectionable quantity is noise in a
    # FLAT region (a clear sky shows noise a reviewer can see; the same sigma in
    # foliage is invisible). The scored value is therefore the noise sigma over
    # the flattest 30% of the frame, which tracks injected noise almost exactly
    # linearly. Calibrated against synthetic ground truth: a clean frame measures
    # 0.0, a lightly grained one ~2, and a visibly noisy one >=20.
    noise_flat_ideal: float = 12.0
    noise_flat_fail: float = 25.0
    #: The old rule penalised noise *below* 0.90 as "flat synthetic texture".
    #: Adobe says the opposite ("noise and artifacts are minimized") and no
    #: source shows a refusal for cleanliness, so a low noise floor is no longer
    #: a defect. The signal is kept as a diagnostic metric only - a genuine
    #: "over-denoised" measure cannot be separated from a legitimately smooth
    #: subject (a sky, a studio backdrop), so scoring it produces false
    #: positives on exactly the images Adobe accepts.
    flat_ratio_tolerance: float = 0.55

    #: A plain weighted mean lets one badly failing dimension be masked by five
    #: passing ones - a 29%-blown image still scored 83%. The overall score is
    #: therefore also capped by the *worst* sub-score, because Adobe's reviewers
    #: reject on any single failed criterion. The ceiling is
    #: ``ceiling_floor + ceiling_span * worst_sub_score``: a perfect worst
    #: dimension (1.0) imposes no cap, while a failing one (0.0) caps the score
    #: at ``ceiling_floor``, which is below any sane threshold.
    #:
    #: The ceiling deliberately uses the worst *decisive* component only. Adobe
    #: reviewers check one box and stop at the first problem, so a decisive
    #: defect must be able to cap the score - but an advisory nitpick (mild
    #: fringing, mild noise) must not, or every image pins at the floor.
    ceiling_floor: float = 0.55
    ceiling_span: float = 0.45

    #: When a critical issue is present (wrong format, sub-4MP, suspected IP)
    #: the image cannot pass at any score. The score is pulled below the
    #: threshold so the number agrees with the verdict.
    critical_cap_margin: float = 0.05

    @classmethod
    def from_settings(cls) -> "AcceptanceConfig":
        """Build a config from application settings, falling back to defaults."""
        return cls(
            threshold=float(getattr(settings, "ACCEPTANCE_THRESHOLD", 0.80)),
            min_megapixels=float(settings.MIN_MEGAPIXELS),
            max_megapixels=float(getattr(settings, "MAX_MEGAPIXELS", 100.0)),
            max_file_size_mb=float(
                getattr(settings, "ABSOLUTE_MAX_FILE_SIZE_MB", 45)
            ),
            sharpness_fail=float(settings.MIN_LAPLACIAN_VARIANCE) / 2.0,
            sharpness_ideal=float(settings.MIN_LAPLACIAN_VARIANCE),
        )


# --------------------------------------------------------------------------- #
# Sub-score builders
# --------------------------------------------------------------------------- #

def _score_technical(metrics: dict[str, float], cfg: AcceptanceConfig) -> SubScore:
    issues: list[Issue] = []
    score = 1.0

    if metrics["is_jpeg"] < 0.5:
        issues.append(
            Issue(WRONG_FORMAT, "critical", "Adobe Stock accepts JPEG only for photos.")
        )
        score -= 0.60

    if metrics["is_srgb"] < 0.5:
        issues.append(
            Issue(
                NOT_SRGB,
                "major",
                "Image is not in the sRGB colour space; Adobe requires an sRGB profile.",
            )
        )
        score -= 0.25
    elif metrics.get("has_icc_profile", 1.0) < 0.5:
        # Adobe's requirement reads "JPEG with sRGB color profile". An untagged
        # file renders as sRGB almost everywhere, so this is a minor warning -
        # but embedding the profile removes the ambiguity entirely, and the
        # export path does it automatically.
        issues.append(
            Issue(
                NOT_SRGB,
                "minor",
                "No ICC profile embedded; Adobe expects an explicit sRGB profile.",
            )
        )
        score -= 0.05

    megapixels = metrics["megapixels"]
    if megapixels < cfg.min_megapixels:
        issues.append(
            Issue(
                LOW_RESOLUTION,
                "critical",
                f"{megapixels:.2f} MP is below the {cfg.min_megapixels:.0f} MP minimum.",
                megapixels,
            )
        )
        score -= 0.60
    elif megapixels > cfg.max_megapixels:
        issues.append(
            Issue(
                EXCESSIVE_RESOLUTION,
                "major",
                f"{megapixels:.1f} MP exceeds the {cfg.max_megapixels:.0f} MP maximum.",
                megapixels,
            )
        )
        score -= 0.20

    file_size = metrics["file_size_mb"]
    if file_size > cfg.max_file_size_mb:
        issues.append(
            Issue(
                FILE_TOO_LARGE,
                "major",
                f"{file_size:.1f} MB exceeds the {cfg.max_file_size_mb:.0f} MB cap.",
                file_size,
            )
        )
        score -= 0.20

    return SubScore(
        "technical",
        SUB_SCORE_LABELS["technical"],
        _clamp(score),
        cfg.weight_technical,
        issues,
        components=[_clamp(score)],
    )


def _score_exposure(metrics: dict[str, float], cfg: AcceptanceConfig) -> SubScore:
    issues: list[Issue] = []
    components: list[float] = []

    highlight_ratio = metrics["clipped_highlight_ratio"]
    highlight_score = 1.0 - _ramp(
        highlight_ratio, cfg.highlight_tolerance, cfg.highlight_fail
    )
    components.append(highlight_score)
    if highlight_ratio > cfg.highlight_tolerance:
        severity = "major" if highlight_ratio > cfg.highlight_fail / 2 else "minor"
        issues.append(
            Issue(
                HIGHLIGHTS_CLIPPED,
                severity,
                f"{highlight_ratio * 100:.2f}% of pixels are pure white (blown highlights).",
                highlight_ratio,
            )
        )

    shadow_ratio = metrics["crushed_shadow_ratio"]
    shadow_score = 1.0 - _ramp(shadow_ratio, cfg.shadow_tolerance, cfg.shadow_fail)
    components.append(shadow_score)
    if shadow_ratio > cfg.shadow_tolerance:
        severity = "major" if shadow_ratio > cfg.shadow_fail / 2 else "minor"
        issues.append(
            Issue(
                SHADOWS_CRUSHED,
                severity,
                f"{shadow_ratio * 100:.2f}% of pixels are pure black (crushed shadows).",
                shadow_ratio,
            )
        )

    return SubScore(
        "exposure",
        SUB_SCORE_LABELS["exposure"],
        _clamp(sum(components) / len(components)),
        cfg.weight_exposure,
        issues,
        components=components,
    )


def _band_score(value: float, fail_low: float, ideal_low: float,
                ideal_high: float, fail_high: float) -> float:
    """Score a value that is best inside ``[ideal_low, ideal_high]``."""
    if ideal_low <= value <= ideal_high:
        return 1.0
    if value < ideal_low:
        return _ramp(value, fail_low, ideal_low)
    return 1.0 - _ramp(value, ideal_high, fail_high)


def _score_color(metrics: dict[str, float], cfg: AcceptanceConfig) -> SubScore:
    issues: list[Issue] = []
    components: list[float] = []

    overall = metrics["overall_saturation"]
    overall_score = _band_score(
        overall, cfg.sat_fail_low, cfg.sat_ideal_low, cfg.sat_ideal_high, cfg.sat_fail_high
    )
    components.append(overall_score)
    if overall > cfg.sat_ideal_high:
        issues.append(
            Issue(
                OVERALL_OVERSATURATED,
                "major" if overall > cfg.sat_fail_high * 0.8 else "minor",
                f"Overall saturation {overall:.2f} is above the natural range.",
                overall,
            )
        )
    elif overall < cfg.sat_ideal_low and metrics["skin_pixel_ratio"] < 0.9:
        # Uniformly desaturated output reads as flat/grey to reviewers.
        issues.append(
            Issue(
                OVERALL_OVERSATURATED,
                "minor",
                f"Overall saturation {overall:.2f} is unusually flat.",
                overall,
            )
        )

    # Only judge skin/green bands when they actually occupy meaningful area.
    skin_ratio = metrics["skin_pixel_ratio"]
    if skin_ratio >= 0.05:
        skin_sat = metrics["skin_saturation"]
        skin_score = 1.0 - _ramp(skin_sat, cfg.skin_sat_ideal, cfg.skin_sat_fail)
        components.append(skin_score)
        if skin_sat > cfg.skin_sat_ideal:
            issues.append(
                Issue(
                    SKIN_TONE_CAST,
                    "major" if skin_sat > cfg.skin_sat_fail * 0.85 else "minor",
                    f"Red/orange saturation {skin_sat:.2f} risks an oversaturated skin cast.",
                    skin_sat,
                )
            )

    green_ratio = metrics["green_pixel_ratio"]
    if green_ratio >= 0.05:
        green_sat = metrics["green_saturation"]
        green_score = 1.0 - _ramp(green_sat, cfg.green_sat_ideal, cfg.green_sat_fail)
        components.append(green_score)
        if green_sat > cfg.green_sat_ideal:
            issues.append(
                Issue(
                    NEON_GREENS,
                    "major" if green_sat > cfg.green_sat_fail * 0.85 else "minor",
                    f"Yellow/green saturation {green_sat:.2f} risks a neon foliage look.",
                    green_sat,
                )
            )

    return SubScore(
        "color",
        SUB_SCORE_LABELS["color"],
        _clamp(sum(components) / len(components)),
        cfg.weight_color,
        issues,
        components=components,
    )


def _score_detail(metrics: dict[str, float], cfg: AcceptanceConfig) -> SubScore:
    issues: list[Issue] = []
    components: list[float] = []
    #: Only these may cap the overall score (see ``SubScore``).
    decisive: list[float] = []

    laplacian = metrics["laplacian_variance"]
    sharpness_score = _ramp(laplacian, cfg.sharpness_fail, cfg.sharpness_ideal)
    components.append(sharpness_score)
    decisive.append(sharpness_score)
    if laplacian < cfg.sharpness_ideal:
        issues.append(
            Issue(
                SOFT_FOCUS,
                "major" if laplacian < cfg.sharpness_fail else "minor",
                f"Sharpness metric {laplacian:.0f} is below the required "
                f"{cfg.sharpness_ideal:.0f} at 100% zoom.",
                laplacian,
            )
        )

    halo_ratio = metrics["halo_ratio"]
    halo_score = 1.0 - _ramp(halo_ratio, cfg.halo_tolerance, cfg.halo_fail)
    components.append(halo_score)
    decisive.append(halo_score)
    if halo_ratio > cfg.halo_tolerance:
        issues.append(
            Issue(
                EDGE_HALO,
                "major" if halo_ratio > cfg.halo_fail * 0.6 else "minor",
                f"{halo_ratio * 100:.1f}% of edge pixels show a bright halo (over-sharpening).",
                halo_ratio,
            )
        )

    # Chromatic aberration: channel MISALIGNMENT, not colour contrast. Adobe
    # lists it as general editing hygiene rather than an AI-specific defect, and
    # community evidence ranks it minor, so it is ADVISORY - it lowers the
    # dimension score but can never cap the overall score on its own.
    misalignment = metrics.get(
        "chroma_misalignment",
        float(metrics.get("chroma_fringe_ratio", 0.0)) * 2.0,
    )
    fringe_score = 1.0 - _ramp(
        misalignment,
        cfg.chroma_misalignment_tolerance,
        cfg.chroma_misalignment_fail,
    )
    components.append(fringe_score)
    if misalignment > cfg.chroma_misalignment_tolerance:
        issues.append(
            Issue(
                CHROMA_FRINGE,
                "major"
                if misalignment > cfg.chroma_misalignment_fail
                else "minor",
                f"Inter-channel misalignment index {misalignment:.2f} indicates "
                f"colour fringing along high-contrast edges.",
                misalignment,
            )
        )

    return SubScore(
        "detail",
        SUB_SCORE_LABELS["detail"],
        _clamp(sum(components) / len(components)),
        cfg.weight_detail,
        issues,
        components=components,
        decisive_components=decisive,
    )


def _score_texture(metrics: dict[str, float], cfg: AcceptanceConfig) -> SubScore:
    issues: list[Issue] = []
    components: list[float] = []
    #: Only these may cap the overall score (see ``SubScore``).
    decisive: list[float] = []

    # Noise is judged where it is VISIBLE. Adobe refused an ISO-160 file for
    # noise because it was a flat blue sky; the same sigma inside foliage is
    # invisible. A global sigma cannot express that, so the flat-region value
    # drives the score and the textured-region value is informational only.
    noise_flat = float(
        metrics.get("noise_sigma_flat", metrics.get("noise_sigma", 0.0))
    )
    noise_score = 1.0 - _ramp(
        noise_flat, cfg.noise_flat_ideal, cfg.noise_flat_fail
    )
    components.append(noise_score)
    decisive.append(noise_score)
    if noise_flat > cfg.noise_flat_ideal:
        issues.append(
            Issue(
                EXCESSIVE_NOISE,
                "major" if noise_flat > cfg.noise_flat_fail else "minor",
                f"Visible noise {noise_flat:.2f} in smooth regions exceeds the "
                f"natural ceiling {cfg.noise_flat_ideal:.2f}.",
                noise_flat,
            )
        )

    # A LOW noise floor is deliberately NOT scored.
    #
    # The old rule penalised ``noise_sigma < 0.90`` as "flat synthetic texture"
    # at MAJOR severity, which capped the overall score at ``ceiling_floor``
    # (0.55) for every clean image - including a real, already-approved Adobe
    # Stock file. Research refuted the premise: Adobe's published guidance is
    # "check that noise and artifacts are MINIMIZED" and no source shows a
    # refusal for cleanliness. The genuine defect behind a "waxy" surface is
    # loss of local micro-detail from over-denoising, which is not reliably
    # separable from a legitimately smooth subject (a sky, a studio backdrop),
    # so it is reported as a diagnostic metric rather than scored.
    return SubScore(
        "texture",
        SUB_SCORE_LABELS["texture"],
        _clamp(sum(components) / len(components)),
        cfg.weight_texture,
        issues,
        components=components,
        decisive_components=decisive,
    )


def _score_semantic(
    semantic: dict | None, cfg: AcceptanceConfig
) -> SubScore | None:
    """Convert an LLM audit result into a sub-score, or None when unavailable."""
    if not semantic:
        return None

    confidence = float(semantic.get("confidence_score", 0.0) or 0.0)
    confidence = _clamp(confidence)
    flags = [str(flag) for flag in (semantic.get("flags") or [])]

    issues: list[Issue] = []
    for flag in flags:
        lowered = flag.lower()
        if any(word in lowered for word in ("logo", "trademark", "brand", "copyright", "ip ")):
            code, severity = POSSIBLE_IP, "critical"
        elif any(word in lowered for word in ("text", "watermark", "signature")):
            code, severity = HALLUCINATED_TEXT, "major"
        else:
            code, severity = SEMANTIC_FLAGGED, "major"
        issues.append(Issue(code, severity, flag))

    # A low score with no specific flag still means the model did not believe in
    # the image, so it must produce an issue - otherwise the ceiling would not
    # react and the total would be diluted by the pixel dimensions.
    if confidence < settings.MIN_SEMANTIC_CONFIDENCE and not flags:
        issues.append(
            Issue(
                SEMANTIC_FLAGGED,
                "major",
                f"Semantic confidence {confidence:.2f} is below the "
                f"{settings.MIN_SEMANTIC_CONFIDENCE:.2f} threshold.",
                confidence,
            )
        )

    return SubScore(
        "semantic",
        SUB_SCORE_LABELS["semantic"],
        confidence,
        cfg.weight_semantic,
        issues,
        components=[confidence],
    )


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def score_image(
    path: str | Path,
    *,
    config: AcceptanceConfig | None = None,
    semantic: dict | None = None,
    metrics: dict[str, float] | None = None,
) -> AcceptanceReport:
    """Compute the full acceptance report for an image.

    Args:
        path: Image file to score.
        config: Optional threshold/weight overrides.
        semantic: Optional LLM audit dict (``confidence_score``, ``flags``) that
            contributes a weighted semantic sub-score.
        metrics: Pre-computed metrics (avoids re-decoding during refinement).

    Returns:
        An :class:`AcceptanceReport` with the weighted score, per-component
        breakdown, and every detected issue.
    """
    cfg = config or AcceptanceConfig.from_settings()

    if metrics is None:
        metrics, _ = pixel_metrics.measure(path)

    sub_scores: dict[str, SubScore] = {
        "technical": _score_technical(metrics, cfg),
        "exposure": _score_exposure(metrics, cfg),
        "color": _score_color(metrics, cfg),
        "detail": _score_detail(metrics, cfg),
        "texture": _score_texture(metrics, cfg),
    }

    semantic_score = _score_semantic(semantic, cfg)
    if semantic_score is not None:
        sub_scores["semantic"] = semantic_score

    # Renormalize weights over whichever sub-scores are present so a missing
    # LLM reply does not silently cap the achievable maximum.
    total_weight = sum(sub.weight for sub in sub_scores.values()) or 1.0
    weighted_mean = (
        sum(sub.score * sub.weight for sub in sub_scores.values()) / total_weight
    )

    issues: list[Issue] = []
    for sub in sub_scores.values():
        issues.extend(sub.issues)

    score = _clamp(weighted_mean)

    # Apply the worst-dimension ceiling so one failed criterion cannot be
    # averaged away by the dimensions that happen to look fine. Using the worst
    # *decisive component* rather than the worst group average is what catches a
    # single failing measurement inside an otherwise healthy group.
    #
    # Only DECISIVE measurements may cap the score. Adobe reviewers check one
    # box and stop at the first problem, so a decisive defect (soft focus,
    # clipping, a colour cast) must be able to pin the score. An advisory signal
    # (mild chromatic fringing, a low noise floor) must not: capping on those is
    # what pinned otherwise-acceptable images at ``ceiling_floor``.
    worst = min(
        (sub.worst_decisive_component for sub in sub_scores.values()), default=1.0
    )
    ceiling = cfg.ceiling_floor + cfg.ceiling_span * worst
    score = _clamp(min(score, ceiling))

    # A critical issue is disqualifying on its own, regardless of the total.
    if any(issue.severity == "critical" for issue in issues):
        score = _clamp(min(score, cfg.threshold - cfg.critical_cap_margin))

    return AcceptanceReport(
        score=score,
        threshold=cfg.threshold,
        passed=score >= cfg.threshold,
        sub_scores=sub_scores,
        issues=issues,
        metrics=metrics,
        semantic_included=semantic_score is not None,
    )
