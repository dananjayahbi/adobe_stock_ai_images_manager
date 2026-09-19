"""Tests for Stage 4 (refinement) and Stage 5 (compatibility gate).

The refiner's contract is: *improve the score, never mutate the source, and
never claim success it did not achieve.* These tests pin all three.
"""

import cv2
import numpy as np
import pytest

from services.acceptance.scorer import AcceptanceConfig
from services.acceptance.types import (
    HIGHLIGHTS_CLIPPED,
    Issue,
    OVERALL_OVERSATURATED,
    POSSIBLE_IP,
    REFINABLE_CODES,
    SHADOWS_CRUSHED,
)
from services.compatibility_checker import check_compatibility
from services.refine import ops
from services.refine.recipe import apply_recipe
from services.refine.refiner import refine_image

from .test_acceptance_scorer import _noisy_gradient, _write


@pytest.fixture()
def lenient_config():
    """A permissive gate so the refiner's *improvement* is what gets measured."""
    return AcceptanceConfig(threshold=0.55)


# --------------------------------------------------------------------------- #
# Individual operations
# --------------------------------------------------------------------------- #

def test_clamp_levels_removes_pure_white_and_black():
    image = np.zeros((50, 50, 3), dtype=np.uint8)
    image[:25, :] = 255
    image[25:, :] = 0

    result = ops.clamp_levels(image, black_point=5, white_point=250)

    assert result.max() == 250
    assert result.min() == 5
    assert result.dtype == np.uint8


def test_clamp_levels_preserves_shape_and_dtype():
    image = _noisy_gradient(400, 300)
    result = ops.clamp_levels(image)

    assert result.shape == image.shape
    assert result.dtype == np.uint8


def test_desaturate_hue_band_lowers_saturation_only_in_band():
    # A pure red frame and a pure blue frame side by side.
    image = np.zeros((60, 120, 3), dtype=np.uint8)
    image[:, :60] = (0, 0, 255)  # BGR red, hue 0
    image[:, 60:] = (255, 0, 0)  # BGR blue, hue 120

    result = ops.desaturate_hue_band(image, 0, 20, factor=0.5)

    red_sat = cv2.cvtColor(result[:, :60], cv2.COLOR_BGR2HSV)[:, :, 1].mean()
    blue_sat = cv2.cvtColor(result[:, 60:], cv2.COLOR_BGR2HSV)[:, :, 1].mean()

    assert red_sat < 255 * 0.9  # the red band was reduced
    assert blue_sat > 250  # the blue band was left alone


def test_desaturate_overall_reduces_saturation():
    image = _noisy_gradient(300, 300)
    before = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)[:, :, 1].mean()

    result = ops.desaturate_overall(image, factor=0.7)
    after = cv2.cvtColor(result, cv2.COLOR_BGR2HSV)[:, :, 1].mean()

    assert after < before


def test_add_sensor_grain_respects_existing_noise():
    """Grain is only added up to the target, never on top of it."""
    image = np.full((200, 200, 3), 128, dtype=np.uint8)

    # An image already noisier than the target must come back untouched.
    already_noisy = ops.add_sensor_grain(image, target_sigma=1.0, current_sigma=3.0)
    assert np.array_equal(already_noisy, image)

    grainy = ops.add_sensor_grain(image, target_sigma=3.0, current_sigma=0.0)
    assert grainy.std() > 1.0
    assert grainy.dtype == np.uint8


def test_defringe_reduces_channel_divergence_on_edges():
    image = np.zeros((120, 120, 3), dtype=np.uint8)
    image[:, :60] = 20
    image[:, 60:] = 235
    # Inject a magenta fringe on the boundary: red and blue both far above green.
    image[:, 58:62, 2] = 255
    image[:, 58:62, 0] = 255

    def purple_excess(frame: np.ndarray) -> float:
        """Mean red/blue-over-green divergence - the fringe itself."""
        data = frame.astype(np.float32)
        blue, green, red = data[:, :, 0], data[:, :, 1], data[:, :, 2]
        excess = np.minimum(
            np.clip(red - green, 0, None), np.clip(blue - green, 0, None)
        )
        return float(excess.mean())

    result = ops.defringe(image, strength=1.0)

    assert purple_excess(result) < purple_excess(image)
    # Green must not be pushed up, which would trade fringing for a green cast.
    assert result[:, :, 1].mean() <= image[:, :, 1].mean() + 1


def test_remove_halo_pulls_back_bright_rims():
    image = np.full((100, 100, 3), 100, dtype=np.uint8)
    image[:, :50] = 40
    # A bright 1px rim just right of the boundary = classic over-sharpen halo.
    image[:, 50:52] = 230

    result = ops.remove_halo(image, strength=1.0)

    assert result[:, 50:52].mean() < 230


def test_sharpen_increases_edge_contrast():
    image = np.full((100, 100, 3), 100, dtype=np.uint8)
    image[:, 50:] = 160
    blurred = cv2.GaussianBlur(image, (0, 0), 2.0)

    result = ops.sharpen(blurred, amount=1.5)
    sharpness_before = cv2.Laplacian(
        cv2.cvtColor(blurred, cv2.COLOR_BGR2GRAY), cv2.CV_64F
    ).var()
    sharpness_after = cv2.Laplacian(
        cv2.cvtColor(result, cv2.COLOR_BGR2GRAY), cv2.CV_64F
    ).var()

    assert sharpness_after > sharpness_before


def test_to_srgb_normalizes_channel_counts():
    gray = np.full((10, 10), 128, dtype=np.uint8)
    rgba = np.full((10, 10, 4), 128, dtype=np.uint8)
    bgr = np.full((10, 10, 3), 128, dtype=np.uint8)

    assert ops.to_srgb(gray).shape == (10, 10, 3)
    assert ops.to_srgb(rgba).shape == (10, 10, 3)
    assert ops.to_srgb(bgr).shape == (10, 10, 3)


# --------------------------------------------------------------------------- #
# Recipe mapping
# --------------------------------------------------------------------------- #

def test_recipe_addresses_clipping_issues():
    image = _noisy_gradient(600, 500)
    issues = [
        Issue(HIGHLIGHTS_CLIPPED, "major", "blown", 0.05),
        Issue(SHADOWS_CRUSHED, "major", "crushed", 0.06),
    ]

    outcome = apply_recipe(image, issues)

    assert outcome.changed
    assert "clamp_levels" in [step.operation for step in outcome.steps]
    assert HIGHLIGHTS_CLIPPED in outcome.addressed
    assert SHADOWS_CRUSHED in outcome.addressed


def test_recipe_ignores_non_refinable_issues():
    image = _noisy_gradient(400, 400)
    issues = [Issue(POSSIBLE_IP, "critical", "suspected logo")]

    outcome = apply_recipe(image, issues)

    assert outcome.changed is False
    assert POSSIBLE_IP in outcome.unaddressable


def test_recipe_scales_strength_with_severity():
    """A worse issue should produce a stronger correction."""
    image = _noisy_gradient(500, 500)

    mild = apply_recipe(
        image, [Issue(OVERALL_OVERSATURATED, "minor", "mild", 0.48)]
    )
    severe = apply_recipe(
        image, [Issue(OVERALL_OVERSATURATED, "major", "severe", 0.72)]
    )

    mild_strength = next(
        s.strength for s in mild.steps if s.operation == "desaturate_overall"
    )
    severe_strength = next(
        s.strength for s in severe.steps if s.operation == "desaturate_overall"
    )

    assert severe_strength > mild_strength


def test_every_refinable_code_has_a_recipe_branch():
    """Guard against an issue code that the scorer emits but nothing can fix."""
    image = _noisy_gradient(300, 300)
    issues = [
        Issue(code, "major", f"test {code}", 1.0) for code in sorted(REFINABLE_CODES)
    ]

    outcome = apply_recipe(image, issues)

    assert set(outcome.addressed) == set(REFINABLE_CODES), (
        f"unhandled refinable codes: {sorted(REFINABLE_CODES - set(outcome.addressed))}"
    )


# --------------------------------------------------------------------------- #
# Refiner loop
# --------------------------------------------------------------------------- #

def test_refiner_never_mutates_the_source(tmp_path, lenient_config):
    image = _noisy_gradient(2000, 1600)
    image[300:1300, 300:1300] = 255  # force refinement work
    source = _write(tmp_path / "source.jpg", image)
    original_bytes = source.read_bytes()

    refine_image(
        source,
        tmp_path / "out",
        "rec-1",
        settings=_settings_for(tmp_path),
        config=lenient_config,
    )

    assert source.read_bytes() == original_bytes


def test_refiner_improves_a_damaged_image(tmp_path):
    image = _noisy_gradient(2000, 1600)
    image[200:1400, 200:1400] = 255
    image[0:100, :] = 0
    source = _write(tmp_path / "damaged.jpg", image)

    config = AcceptanceConfig(threshold=0.55)
    result = refine_image(
        source,
        tmp_path / "out",
        "rec-2",
        settings=_settings_for(tmp_path),
        config=config,
    )

    assert result.initial_score < 0.80, "fixture should start non-compliant"
    assert result.final_score > result.initial_score, (
        f"refiner did not improve: {result.initial_score:.3f} -> "
        f"{result.final_score:.3f}, history={result.history}"
    )
    assert result.output_path is not None
    assert (tmp_path / "out" / "rec-2-refined.jpg").exists()


def test_refiner_reports_failure_when_threshold_is_unreachable(tmp_path):
    """A flat image cannot be repaired by pixel tweaks alone - it must say so."""
    flat = np.full((1600, 1200, 3), 128, dtype=np.uint8)
    source = _write(tmp_path / "flat.jpg", flat)

    result = refine_image(
        source,
        tmp_path / "out",
        "rec-3",
        settings=_settings_for(tmp_path),
        config=AcceptanceConfig(threshold=0.99),
    )

    assert result.success is False
    assert "below" in result.reason
    # It must still hand back the best attempt rather than nothing.
    assert result.output_path is not None


def test_refiner_short_circuits_a_compliant_image(tmp_path, lenient_config):
    source = _write(tmp_path / "good.jpg", _noisy_gradient())

    result = refine_image(
        source,
        tmp_path / "out",
        "rec-4",
        settings=_settings_for(tmp_path),
        config=lenient_config,
    )

    assert result.success is True
    assert result.passes == 0
    assert "No refinement needed" in result.reason


def test_refiner_cleans_up_scratch_pass_files(tmp_path, lenient_config):
    image = _noisy_gradient(2000, 1600)
    image[300:1300, 300:1300] = 255
    source = _write(tmp_path / "source.jpg", image)

    refine_image(
        source,
        tmp_path / "out",
        "rec-5",
        settings=_settings_for(tmp_path),
        config=lenient_config,
    )

    scratch = list((tmp_path / "out").glob("rec-5-pass*.jpg"))
    assert scratch == [], f"scratch files left behind: {scratch}"


def test_refiner_handles_missing_file(tmp_path, lenient_config):
    result = refine_image(
        tmp_path / "nope.jpg",
        tmp_path / "out",
        "rec-6",
        settings=_settings_for(tmp_path),
        config=lenient_config,
    )

    assert result.success is False
    assert "not found" in result.reason.lower()


# --------------------------------------------------------------------------- #
# Stage 5 gate
# --------------------------------------------------------------------------- #

def test_compatibility_gate_passes_a_clean_image(tmp_path):
    source = _write(tmp_path / "clean.jpg", _noisy_gradient())

    verdict = check_compatibility(source, config=AcceptanceConfig(threshold=0.55))

    assert verdict.passed is True
    assert verdict.remediation == []
    assert "Compatible" in verdict.summary
    assert verdict.score >= 0.55


def test_compatibility_gate_fails_a_damaged_image_with_advice(tmp_path):
    image = _noisy_gradient()
    image[200:1400, 200:1600] = 255
    source = _write(tmp_path / "damaged.jpg", image)

    verdict = check_compatibility(source, config=AcceptanceConfig(threshold=0.95))

    assert verdict.passed is False
    assert verdict.remediation, "a failing verdict must carry remediation advice"
    assert any("white point" in hint for hint in verdict.remediation)


def test_compatibility_gate_includes_semantic_flags(tmp_path):
    source = _write(tmp_path / "clean.jpg", _noisy_gradient())

    verdict = check_compatibility(
        source,
        semantic={"confidence_score": 0.2, "flags": ["suspected brand logo on shoe"]},
        config=AcceptanceConfig(threshold=0.80),
    )

    codes = {issue.code for issue in verdict.report.issues}
    assert POSSIBLE_IP in codes
    assert verdict.passed is False


def test_compatibility_serializes(tmp_path):
    source = _write(tmp_path / "clean.jpg", _noisy_gradient())
    verdict = check_compatibility(source, config=AcceptanceConfig(threshold=0.55))
    payload = verdict.to_dict()

    assert set(payload) >= {"passed", "score", "summary", "remediation", "report"}
    assert isinstance(payload["report"], dict)


def _settings_for(tmp_path):
    """A settings object with Stage 3/4 directories redirected into tmp_path."""
    from config import settings

    return settings.model_copy(
        update={
            "REFINED_DIR": tmp_path / "out",
            "UPSCALED_DIR": tmp_path / "up",
            "MAX_REFINE_PASSES": 4,
            "EXPORT_JPEG_QUALITY": 95,
        }
    )
