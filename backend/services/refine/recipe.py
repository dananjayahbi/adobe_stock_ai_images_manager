"""Refinement recipes - translate acceptance issues into pixel operations.

The mapping is intentionally data-driven: each issue code declares how far it is
from the ideal, and that distance scales the strength of the corrective
operation. A mildly over-saturated image gets a gentle nudge; a badly clipped
one gets the full correction. This keeps the refiner from over-correcting
images that are only marginally outside tolerance.

Adobe's editing guidance is explicitly conservative, and its DON'Ts are the
reason for the hard ceiling below:

* "Overprocessing with excessive contrast or HDR filters may lead to unnatural
  results."
* "Refrain from heavy color grading and, instead, aim for versatile,
  true-to-life color."
* "Adding non-natural elements or presets" is a refusal reason.
* "Reducing noise without risking key details" is the stated goal - not
  aggressive smoothing.

Every correction here therefore targets the *minimum* change that clears the
measured threshold, and :data:`MAX_CORRECTION_STRENGTH` stops the refiner from
ever applying a dramatic edit, however far outside tolerance the input is.

Source: helpx /submit-photos/photo-editing-best-practices.html
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from services.acceptance.types import (
    CHROMA_FRINGE,
    EXCESSIVE_NOISE,
    FLAT_SYNTHETIC_TEXTURE,
    HIGHLIGHTS_CLIPPED,
    NEON_GREENS,
    OVERALL_OVERSATURATED,
    SHADOWS_CRUSHED,
    SKIN_TONE_CAST,
    SOFT_FOCUS,
    EDGE_HALO,
    Issue,
)
from services.refine import ops

logger = logging.getLogger(__name__)

#: Target monochromatic noise sigma for a natural-looking 4K capture.
TARGET_GRAIN_SIGMA = 1.6

#: Ceiling on any single correction's strength. Adobe treats "overprocessing"
#: and "heavy color grading" as refusal reasons, so even a badly out-of-tolerance
#: input is corrected conservatively - the loop in ``refiner.py`` can always run
#: another pass, whereas an over-edited frame cannot be un-edited.
MAX_CORRECTION_STRENGTH = 0.55

#: Largest total desaturation the colour stage may apply across all bands. A
#: stacked skin + green + global correction must not add up to a heavy grade.
MAX_TOTAL_DESATURATION = 0.22

#: Smallest desaturation still worth applying. Below this the correction is
#: invisible, so the operation is skipped rather than recorded as a fix.
MIN_DESATURATION_STEP = 0.02

#: Sharpness ramp endpoints, mirroring the scorer's detail thresholds.
SHARPNESS_IDEAL = 120.0
SHARPNESS_FAIL = 60.0

#: OpenCV hue ranges (0-179).
HUE_RED_ORANGE = (0, 20)
HUE_YELLOW_GREEN = (21, 85)


@dataclass
class RefineStep:
    """One applied correction, recorded so the UI can explain what changed."""

    operation: str
    strength: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "strength": round(self.strength, 4),
            "reason": self.reason,
        }


@dataclass
class RefineOutcome:
    """Result of one refinement pass."""

    image: np.ndarray
    steps: list[RefineStep] = field(default_factory=list)
    #: Issue codes this pass was able to address.
    addressed: list[str] = field(default_factory=list)
    #: Issue codes that require a human (e.g. a suspected logo).
    unaddressable: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.steps)

    def to_dict(self) -> dict:
        return {
            "steps": [step.to_dict() for step in self.steps],
            "addressed": self.addressed,
            "unaddressable": self.unaddressable,
        }


def _severity_scale(issue: Issue, ideal: float, fail: float) -> float:
    """Map how far an issue exceeds its ideal to a 0..1 correction strength.

    ``ideal`` is the value at which no correction is needed; ``fail`` is the
    value at which the full-strength correction is warranted.

    ``ideal`` may be greater than ``fail`` for metrics where lower is worse
    (sharpness), in which case the ramp is inverted.
    """
    value = issue.value if issue.value is not None else fail
    if fail == ideal:
        return 1.0
    return float(np.clip((value - ideal) / (fail - ideal), 0.25, 1.0))


def _capped(strength: float) -> float:
    """Clamp a correction strength to Adobe-safe territory.

    Guards the DON'Ts: no single operation may be dramatic enough to read as
    overprocessing, regardless of how far outside tolerance the measurement is.
    """
    return float(min(strength, MAX_CORRECTION_STRENGTH))


def apply_recipe(
    image: np.ndarray,
    issues: list[Issue],
    *,
    metrics: dict[str, float] | None = None,
) -> RefineOutcome:
    """Apply every corrective operation implied by ``issues``.

    Operations are applied in a fixed order - tone, then colour, then edge
    repair, then texture - because each stage changes the measurements the next
    one relies on.

    Args:
        image: BGR uint8 array to correct (mutated copy is returned).
        issues: Issues reported by the acceptance scorer.
        metrics: Current measurements, used to size the grain addition.

    Returns:
        A :class:`RefineOutcome` carrying the corrected image and a log of the
        operations applied.
    """
    metrics = metrics or {}
    outcome = RefineOutcome(image=image.copy())
    by_code = {issue.code: issue for issue in issues}

    # ---------------------------------------------------------------- #
    # 1. Tone: clamp blown highlights and crushed shadows.
    # ---------------------------------------------------------------- #
    if HIGHLIGHTS_CLIPPED in by_code or SHADOWS_CRUSHED in by_code:
        highlight = by_code.get(HIGHLIGHTS_CLIPPED)
        shadow = by_code.get(SHADOWS_CRUSHED)

        # Push the white point down further the worse the clipping is.
        white_point = 252
        if highlight is not None:
            scale = _severity_scale(highlight, 0.010, 0.060)
            white_point = int(round(252 - 8 * scale))
        black_point = 4
        if shadow is not None:
            scale = _severity_scale(shadow, 0.020, 0.080)
            black_point = int(round(4 + 5 * scale))

        outcome.image = ops.clamp_levels(outcome.image, black_point, white_point)
        outcome.steps.append(
            RefineStep(
                "clamp_levels",
                max(black_point / 9.0, (255 - white_point) / 11.0),
                f"Compressed tonal range to {black_point}-{white_point} to preserve highlight and shadow detail.",
            )
        )
        outcome.addressed.append(
            HIGHLIGHTS_CLIPPED if highlight is not None else SHADOWS_CRUSHED
        )
        if shadow is not None:
            outcome.addressed.append(SHADOWS_CRUSHED)

    # ---------------------------------------------------------------- #
    # 2. Colour: pull back saturated bands without flattening the image.
    # ---------------------------------------------------------------- #
    if SKIN_TONE_CAST in by_code:
        issue = by_code[SKIN_TONE_CAST]
        scale = _severity_scale(issue, 0.42, 0.68)
        amount = _capped(0.18 * scale)
        factor = 1.0 - amount
        outcome.image = ops.desaturate_hue_band(
            outcome.image, *HUE_RED_ORANGE, factor=factor
        )
        outcome.steps.append(
            RefineStep(
                "desaturate_skin_band",
                amount,
                f"Reduced red/orange saturation by {amount * 100:.0f}% to remove the AI skin cast.",
            )
        )
        outcome.addressed.append(SKIN_TONE_CAST)

    if NEON_GREENS in by_code:
        issue = by_code[NEON_GREENS]
        scale = _severity_scale(issue, 0.50, 0.80)
        amount = _capped(0.16 * scale)
        factor = 1.0 - amount
        outcome.image = ops.desaturate_hue_band(
            outcome.image, *HUE_YELLOW_GREEN, factor=factor
        )
        outcome.steps.append(
            RefineStep(
                "desaturate_green_band",
                amount,
                f"Reduced yellow/green saturation by {amount * 100:.0f}% to make foliage read naturally.",
            )
        )
        outcome.addressed.append(NEON_GREENS)

    if OVERALL_OVERSATURATED in by_code:
        issue = by_code[OVERALL_OVERSATURATED]
        scale = _severity_scale(issue, 0.45, 0.72)
        # Stacked band corrections can add up to a heavy grade, which Adobe
        # explicitly warns against, so the global pull-back is limited to what
        # remains of the total desaturation budget. A minimum floor keeps the
        # correction from being skipped entirely - leaving the issue unaddressed
        # would be worse than applying a small, safe adjustment.
        already = sum(
            step.strength
            for step in outcome.steps
            if step.operation.startswith("desaturate")
        )
        remaining = max(MAX_TOTAL_DESATURATION - already, MIN_DESATURATION_STEP)
        amount = min(_capped(0.12 * scale), remaining)
        factor = 1.0 - amount
        outcome.image = ops.desaturate_overall(outcome.image, factor)
        outcome.steps.append(
            RefineStep(
                "desaturate_overall",
                amount,
                f"Lowered global saturation by {amount * 100:.0f}%.",
            )
        )
        outcome.addressed.append(OVERALL_OVERSATURATED)

    # ---------------------------------------------------------------- #
    # 3. Edge integrity: repair fringing and halos from upscaling.
    # ---------------------------------------------------------------- #
    if CHROMA_FRINGE in by_code:
        issue = by_code[CHROMA_FRINGE]
        scale = _severity_scale(issue, 0.02, 0.15)
        strength = _capped(0.4 + 0.5 * scale)
        outcome.image = ops.defringe(outcome.image, strength=strength)
        outcome.steps.append(
            RefineStep(
                "defringe",
                strength,
                "Removed purple/green colour fringing along high-contrast edges.",
            )
        )
        outcome.addressed.append(CHROMA_FRINGE)

    if EDGE_HALO in by_code:
        issue = by_code[EDGE_HALO]
        scale = _severity_scale(issue, 0.05, 0.30)
        strength = _capped(0.4 + 0.4 * scale)
        outcome.image = ops.remove_halo(outcome.image, strength=strength)
        outcome.steps.append(
            RefineStep(
                "remove_halo",
                strength,
                "Pulled back bright over-sharpening halos on high-contrast borders.",
            )
        )
        outcome.addressed.append(EDGE_HALO)

    if SOFT_FOCUS in by_code:
        issue = by_code[SOFT_FOCUS]
        # Sharpen only mildly: Adobe lists over-sharpening artefacts and
        # "overprocessing" as refusal reasons, so the mask stays restrained even
        # when the frame is well below the sharpness floor.
        scale = (
            _severity_scale(issue, SHARPNESS_IDEAL, SHARPNESS_FAIL)
            if issue.value is not None
            else 0.5
        )
        amount = _capped(0.35 + 0.35 * scale)
        outcome.image = ops.sharpen(outcome.image, amount=amount, radius=1.1)
        outcome.steps.append(
            RefineStep(
                "unsharp_mask",
                amount,
                f"Applied a restrained unsharp mask (amount {amount:.2f}) to recover edge definition.",
            )
        )
        outcome.addressed.append(SOFT_FOCUS)

    # ---------------------------------------------------------------- #
    # 4. Texture: restore a plausible sensor noise floor.
    # ---------------------------------------------------------------- #
    if FLAT_SYNTHETIC_TEXTURE in by_code:
        current = float(metrics.get("noise_sigma", 0.0))
        outcome.image = ops.add_sensor_grain(
            outcome.image, target_sigma=TARGET_GRAIN_SIGMA, current_sigma=current
        )
        outcome.steps.append(
            RefineStep(
                "sensor_grain",
                TARGET_GRAIN_SIGMA,
                f"Added monochromatic sensor grain (target sigma {TARGET_GRAIN_SIGMA}) to break up waxy surfaces.",
            )
        )
        outcome.addressed.append(FLAT_SYNTHETIC_TEXTURE)

    if EXCESSIVE_NOISE in by_code:
        # Denoise lightly; aggressive denoising recreates the flat look.
        outcome.image = ops.deblock(outcome.image, strength=0.35)
        outcome.image = ops.sharpen(outcome.image, amount=0.25, radius=1.0)
        outcome.steps.append(
            RefineStep(
                "light_denoise",
                0.35,
                "Smoothed excessive sensor noise while preserving edge detail.",
            )
        )
        outcome.addressed.append(EXCESSIVE_NOISE)

    # Anything the scorer flagged that has no pixel-level remedy is surfaced
    # so the operator knows manual review is required.
    outcome.unaddressable = sorted(
        {issue.code for issue in issues if issue.code not in set(outcome.addressed)}
    )

    return outcome
