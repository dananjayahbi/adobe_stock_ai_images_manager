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


#: Absolute ceiling an escalated correction may reach. Above this the edit would
#: read as the heavy colour grading and overprocessing Adobe lists as refusal
#: reasons, even if it would score better.
ABSOLUTE_MAX_STRENGTH = 0.85


def _capped(strength: float, escalation: float = 1.0) -> float:
    """Clamp a correction strength to Adobe-safe territory.

    Guards the DON'Ts: no single operation may be dramatic enough to read as
    overprocessing, regardless of how far outside tolerance the measurement is.

    ``escalation`` scales the correction for *repeated* attempts on the same
    image. This exists because the recipe is otherwise idempotent: the strength
    is a pure function of the measured issue, so re-running it on its own output
    recomputes the identical strength and produces an identical image. That is
    why an earlier auto-fix could report "fixed 4 issues" while the score did
    not move by a single point. A caller that wants to make real progress must
    ask for progressively stronger corrections - and this clamp is what stops
    that progression from ever reaching an un-exportable edit.

    At ``escalation == 1.0`` the limit is exactly :data:`MAX_CORRECTION_STRENGTH`,
    so the single-shot behaviour is unchanged; it only opens up as the caller
    escalates, and never past :data:`ABSOLUTE_MAX_STRENGTH`.
    """
    factor = max(1.0, escalation)
    limit = min(MAX_CORRECTION_STRENGTH * factor, ABSOLUTE_MAX_STRENGTH)
    return float(min(strength * factor, limit))


def apply_recipe(
    image: np.ndarray,
    issues: list[Issue],
    *,
    metrics: dict[str, float] | None = None,
    escalation: float = 1.0,
) -> RefineOutcome:
    """Apply every corrective operation implied by ``issues``.

    Operations are applied in a fixed order - tone, then colour, then edge
    repair, then texture - because each stage changes the measurements the next
    one relies on.

    Args:
        image: BGR uint8 array to correct (mutated copy is returned).
        issues: Issues reported by the acceptance scorer.
        metrics: Current measurements, used to size the grain addition.
        escalation: Multiplier on every correction strength. 1.0 is the default
            single-shot behaviour; the adaptive auto-fix loop raises it on each
            retry so a stalled metric actually moves. Clamped internally to
            :data:`ABSOLUTE_MAX_STRENGTH`.

    Returns:
        A :class:`RefineOutcome` carrying the corrected image and a log of the
        operations applied.
    """
    metrics = metrics or {}
    outcome = RefineOutcome(image=image.copy())
    by_code = {issue.code: issue for issue in issues}
    cap = lambda strength: _capped(strength, escalation)  # noqa: E731

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
        amount = cap(0.18 * scale)
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
        amount = cap(0.16 * scale)
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
        # The total-desaturation budget is a *composition* limit, not a
        # per-pass one, so it scales with the escalation too. Otherwise a retry
        # would be blocked by the desaturation the previous pass already spent.
        budget = min(MAX_TOTAL_DESATURATION * max(1.0, escalation), ABSOLUTE_MAX_STRENGTH)
        remaining = max(budget - already, MIN_DESATURATION_STEP)
        amount = min(cap(0.12 * scale), remaining)
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
        strength = cap(0.4 + 0.5 * scale)
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
        strength = cap(0.4 + 0.4 * scale)
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
        amount = cap(0.35 + 0.35 * scale)
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
    # 4. Texture: restore local detail (never fake a noise floor).
    # ---------------------------------------------------------------- #
    # The old branch added synthetic grain to raise ``noise_sigma`` to a
    # "natural" floor. Research refuted that: Adobe's guidance is that noise be
    # *minimised* and that files carry "no added grain, filters or textures", so
    # the fix addressed a property Adobe does not want. The genuine defect
    # behind a "waxy" surface is loss of local micro-detail, which is restored
    # directly.
    if FLAT_SYNTHETIC_TEXTURE in by_code:
        amount = cap(0.55)
        outcome.image = ops.restore_texture(outcome.image, amount=amount)
        outcome.steps.append(
            RefineStep(
                "restore_texture",
                amount,
                f"Restored local micro-detail (amount {amount:.2f}) on "
                "over-smoothed surfaces without adding synthetic grain.",
            )
        )
        outcome.addressed.append(FLAT_SYNTHETIC_TEXTURE)

    if EXCESSIVE_NOISE in by_code:
        # Denoise only where noise is visible, and give back the micro-detail
        # the filter removes - Adobe refuses "unrealistic skin-smoothing" as
        # readily as it refuses noise. Strength escalates, because one light
        # pass does not always bring a noisy frame under the ceiling.
        denoise_strength = cap(0.60)
        outcome.image = ops.denoise_flat_regions(
            outcome.image, strength=denoise_strength
        )
        outcome.steps.append(
            RefineStep(
                "denoise_flat_regions",
                denoise_strength,
                "Suppressed noise where it is visible (flat regions) while "
                "preserving texture detail elsewhere.",
            )
        )
        outcome.addressed.append(EXCESSIVE_NOISE)

    # Anything the scorer flagged that has no pixel-level remedy is surfaced
    # so the operator knows manual review is required.
    outcome.unaddressable = sorted(
        {issue.code for issue in issues if issue.code not in set(outcome.addressed)}
    )

    return outcome
