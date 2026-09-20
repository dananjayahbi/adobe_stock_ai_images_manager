"""Tests for the acceptance scorer and its pixel measurements.

These pin the *behaviour* that Stage 4 and Stage 5 depend on: a clean image
scores above the gate, a deliberately damaged image scores below it, and the
issue codes that drive the refiner are actually emitted.
"""

import cv2
import numpy as np
import pytest
from PIL import Image

from services.acceptance import pixel_metrics
from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import (
    CHROMA_FRINGE,
    FLAT_SYNTHETIC_TEXTURE,
    HIGHLIGHTS_CLIPPED,
    LOW_RESOLUTION,
    NOT_SRGB,
    OVERALL_OVERSATURATED,
    POSSIBLE_IP,
    SEMANTIC_FLAGGED,
    SHADOWS_CRUSHED,
    WRONG_FORMAT,
)


def _noisy_gradient(width: int = 2400, height: int = 2000, seed: int = 7) -> np.ndarray:
    """A natural-looking image: smooth gradient, fine detail, and a noise floor.

    This is the "should pass" baseline. It has mid-tones (no clipping), moderate
    saturation, genuine high-frequency detail (so the sharpness metric sees what
    a real lens resolves at 1:1), and a plausible sensor noise floor.

    A *purely* smooth gradient would correctly fail the sharpness check - a real
    reviewer calls that soft - so the fine-detail terms matter.
    """
    rng = np.random.default_rng(seed)

    x = np.linspace(0, 1, width, dtype=np.float32)
    y = np.linspace(0, 1, height, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(x, y)

    # A smooth blue-green-to-warm gradient with a soft radial highlight.
    radius = np.sqrt((grid_x - 0.5) ** 2 + (grid_y - 0.5) ** 2)
    blue = 90 + 70 * (1 - radius)
    green = 110 + 60 * grid_y
    red = 120 + 50 * grid_x

    image = np.stack([blue, green, red], axis=2)

    # Mid-frequency modulation: broad tonal variation, not "flat".
    image += (22 * np.sin(grid_x * 34) * np.cos(grid_y * 27))[:, :, None]

    # Fine detail at roughly a 10-pixel period - the scale a sharp lens resolves
    # and the scale Adobe's 100% zoom inspection actually judges.
    fine = (
        14 * np.sin(grid_x * 240) * np.cos(grid_y * 205)
        + 9 * np.sin(grid_x * 415 + grid_y * 330)
    )
    image += fine[:, :, None]

    # A realistic monochromatic noise floor.
    image += rng.normal(0, 2.4, size=(height, width, 1))

    return np.clip(image, 0, 255).astype(np.uint8)


def _write(path, array: np.ndarray, quality: int = 97):
    cv2.imwrite(
        str(path),
        array,
        [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_CHROMA_QUALITY, 100],
    )
    return path


@pytest.fixture()
def clean_image(tmp_path):
    return _write(tmp_path / "clean.jpg", _noisy_gradient())


@pytest.fixture()
def config():
    return AcceptanceConfig.from_settings()


# --------------------------------------------------------------------------- #
# Baseline behaviour
# --------------------------------------------------------------------------- #

def test_clean_image_scores_above_threshold(clean_image, config):
    report = score_image(clean_image, config=config)

    assert report.passed is True, (
        f"expected a pass, got {report.score:.3f} with issues "
        f"{[i.code for i in report.issues]}"
    )
    assert report.score >= 0.80
    assert report.confidence_percent >= 80


def test_report_serializes_and_round_trips(clean_image, config):
    report = score_image(clean_image, config=config)
    payload = report.to_dict()

    assert set(payload) >= {
        "score",
        "confidence_percent",
        "threshold",
        "passed",
        "sub_scores",
        "issues",
        "metrics",
    }

    from services.acceptance.types import AcceptanceReport

    restored = AcceptanceReport.from_dict(payload)
    # ``to_dict`` rounds to 4 decimals to keep the stored JSON compact, so the
    # round trip is accurate to that precision rather than bit-exact.
    assert restored.score == pytest.approx(report.score, abs=1e-4)
    assert restored.passed == report.passed
    assert set(restored.sub_scores) == set(report.sub_scores)
    assert [i.code for i in restored.issues] == [i.code for i in report.issues]


def test_missing_semantic_renormalizes_weights(clean_image, config):
    """Without an LLM reply the score must not be capped at the weight sum."""
    without = score_image(clean_image, config=config)
    with_semantic = score_image(
        clean_image,
        config=config,
        semantic={"confidence_score": 0.95, "flags": []},
    )

    assert without.semantic_included is False
    assert with_semantic.semantic_included is True
    assert "semantic" in with_semantic.sub_scores
    assert "semantic" not in without.sub_scores
    # Both are legitimate full-scale scores, not scaled-down fractions.
    assert without.score > 0.7


# --------------------------------------------------------------------------- #
# Issue detection
# --------------------------------------------------------------------------- #

def test_blown_highlights_are_detected(tmp_path, config):
    image = _noisy_gradient()
    # Blow out a large block to pure white.
    image[200:1200, 200:1600] = 255
    path = _write(tmp_path / "blown.jpg", image)

    report = score_image(path, config=config)
    codes = {issue.code for issue in report.issues}

    assert HIGHLIGHTS_CLIPPED in codes
    assert report.passed is False


def test_crushed_shadows_are_detected(tmp_path, config):
    image = _noisy_gradient()
    image[200:1400, 200:1600] = 0
    path = _write(tmp_path / "crushed.jpg", image)

    report = score_image(path, config=config)
    codes = {issue.code for issue in report.issues}

    assert SHADOWS_CRUSHED in codes


def test_oversaturation_is_detected(tmp_path, config):
    image = _noisy_gradient()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * 3.0, 0, 255)
    saturated = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    path = _write(tmp_path / "saturated.jpg", saturated)

    report = score_image(path, config=config)
    codes = {issue.code for issue in report.issues}

    assert OVERALL_OVERSATURATED in codes
    assert report.passed is False


def test_flat_image_is_not_flagged_as_synthetic(tmp_path, config):
    """A perfectly flat surface must NOT be penalised for having no noise.

    This test previously asserted the opposite ("a flat surface has no noise
    floor - the 'waxy AI' tell"), and that rule was the reason **every** image
    scored exactly 55%: it emitted a MAJOR ``flat_synthetic_texture`` issue,
    which capped the score at ``ceiling_floor``.

    Research refuted the premise. Adobe's published guidance is "check that
    noise and artifacts are **minimized**" and that files carry "**no added
    grain**, filters or textures"; no source shows a refusal for cleanliness. A
    flat surface is also exactly what a legitimate subject (a studio backdrop, a
    clear sky) looks like, so the check could not be made precise enough to keep.

    The test now pins the honest contract: a flat image may fail on genuine
    grounds (a synthetic fixture is below the 4 MP floor and is genuinely soft),
    but never on the false "no sensor noise" tell.
    """
    flat = np.full((2000, 2400, 3), 150, dtype=np.uint8)
    path = _write(tmp_path / "flat.jpg", flat)

    report = score_image(path, config=config)
    codes = {issue.code for issue in report.issues}

    assert FLAT_SYNTHETIC_TEXTURE not in codes, (
        "a clean image was penalised for having no sensor noise"
    )
    # The texture dimension must not be dragged down by the absence of noise.
    assert report.sub_scores["texture"].score == pytest.approx(1.0)


def test_chroma_fringing_is_detected(tmp_path, config):
    """Fringing is a *channel misalignment*, not merely a colourful edge.

    A saturated but smooth colour boundary (a red flower on green foliage) is
    legitimate photography and must not be flagged. Real fringing shows up as a
    spiky difference channel at the edge, so the test injects per-pixel channel
    offsets along a high-contrast boundary.
    """
    image = _noisy_gradient()
    height, width = image.shape[:2]

    # A strong vertical boundary, then shift red and blue by one pixel in
    # opposite directions - exactly what lens/upscaler aberration does.
    image[:, width // 2 :] = np.clip(
        image[:, width // 2 :].astype(np.int16) + 120, 0, 255
    ).astype(np.uint8)

    fringed = image.copy()
    fringed[:, :, 2] = np.roll(image[:, :, 2], 2, axis=1)  # red shifted right
    fringed[:, :, 0] = np.roll(image[:, :, 0], -2, axis=1)  # blue shifted left

    path = _write(tmp_path / "fringe.jpg", fringed)
    report = score_image(path, config=config)

    assert CHROMA_FRINGE in {issue.code for issue in report.issues}


def test_smooth_colour_boundary_is_not_fringing(tmp_path, config):
    """A saturated edge with aligned channels must not be reported as fringing.

    This is the regression that made the old detector useless: it measured the
    ``R-G``/``B-G`` colour-difference channel, so a saturated boundary (a 170-unit
    step in that channel) registered as aberration. It fired on essentially every
    image, including a real approved Adobe Stock photo, and it did not even
    increase with the amount of aberration.

    Written as **PNG** deliberately. JPEG uses chroma subsampling, which physically
    misaligns the channels at a hard colour boundary - measured: the same array
    scores 0.00 lossless but 1.98 as JPEG 4:2:0. That is a genuine encoding defect,
    not a false positive, so a JPEG cannot be used to test the "channels aligned"
    property.
    """
    image = _noisy_gradient()
    width = image.shape[1]
    # Strong red/green colour split, but every channel aligned - so no fringe.
    image[:, width // 2 :, 2] = 230
    image[:, width // 2 :, 1] = 90
    image[:, : width // 2, 2] = 60
    image[:, : width // 2, 1] = 200

    path = tmp_path / "colourful.png"
    cv2.imwrite(str(path), image)
    report = score_image(str(path), config=config)

    assert CHROMA_FRINGE not in {issue.code for issue in report.issues}


def test_jpeg_chroma_subsampling_at_a_hard_colour_edge_is_reported(tmp_path, config):
    """Chroma subsampling at a saturated boundary IS a real misalignment.

    Documented because it looks like a false positive but is not: the lossless and
    JPEG encodes of one identical array differ by ~2.0 on the misalignment index
    (measured 0.00 as PNG vs 1.98 as JPEG 4:2:0).

    The assertion is on the *metric* rather than the emitted issue, because the
    issue is only raised past ``chroma_misalignment_tolerance`` and this frame's
    hard edge is narrow relative to the frame. What matters is that the detector
    sees the misalignment at all.
    """
    from services.acceptance import chroma

    image = _noisy_gradient()
    width = image.shape[1]
    image[:, width // 2 :, 2] = 230
    image[:, width // 2 :, 1] = 90
    image[:, : width // 2, 2] = 60
    image[:, : width // 2, 1] = 200

    jpeg = cv2.imread(str(_write(tmp_path / "colourful.jpg", image)))
    png = cv2.imread(str(_write(tmp_path / "colourful.png", image)))

    jpeg_index = chroma.measure_channel_misalignment(jpeg)
    png_index = chroma.measure_channel_misalignment(png)

    assert png_index < 0.05, f"lossless encode reported {png_index:.3f}"
    assert jpeg_index > png_index + 0.2, (
        f"subsampling not detected: jpeg={jpeg_index:.3f} png={png_index:.3f}"
    )
    assert jpeg_index > config.chroma_misalignment_tolerance


def test_solid_two_colour_graphic_is_not_fringing(tmp_path, config):
    """A graphic with one hard edge and flat interiors must not read as fringing.

    Flat interiors carry only quantisation noise in each channel's Laplacian, and
    that noise is uncorrelated between channels - so a purely percentile-based
    edge mask selects mostly flat pixels here and reports misalignment.
    """
    graphic = np.zeros((1200, 1600, 3), dtype=np.uint8)
    graphic[:, :800] = (255, 0, 0)
    graphic[:, 800:] = (0, 255, 0)

    path = tmp_path / "graphic.png"
    cv2.imwrite(str(path), graphic)
    report = score_image(str(path), config=config)

    assert CHROMA_FRINGE not in {issue.code for issue in report.issues}


def test_low_resolution_is_blocking(tmp_path, config):
    small = _noisy_gradient(width=800, height=600)
    path = _write(tmp_path / "small.jpg", small)

    report = score_image(path, config=config)
    codes = {issue.code for issue in report.issues}

    assert LOW_RESOLUTION in codes
    assert report.passed is False


def test_non_jpeg_is_blocking(tmp_path, config):
    path = tmp_path / "image.png"
    Image.fromarray(
        cv2.cvtColor(_noisy_gradient(1200, 1000), cv2.COLOR_BGR2RGB)
    ).save(path)

    report = score_image(path, config=config)

    assert WRONG_FORMAT in {issue.code for issue in report.issues}
    assert report.passed is False


def test_unreadable_file_does_not_raise(tmp_path, config):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"not actually a jpeg")

    report = score_image(path, config=config)

    assert report.passed is False
    assert report.score < 0.80


# --------------------------------------------------------------------------- #
# Measurement layer
# --------------------------------------------------------------------------- #

def test_measure_returns_every_expected_metric(clean_image):
    metrics, image = pixel_metrics.measure(clean_image)

    expected = {
        "clipped_highlight_ratio",
        "crushed_shadow_ratio",
        "mean_luma",
        "luma_std",
        "overall_saturation",
        "skin_saturation",
        "green_saturation",
        "laplacian_variance",
        "halo_ratio",
        "chroma_fringe_ratio",
        "noise_sigma",
        "flat_region_ratio",
        "megapixels",
        "file_size_mb",
        "is_jpeg",
        "is_srgb",
    }
    assert expected <= set(metrics)
    assert image is not None
    assert metrics["is_jpeg"] == 1.0
    assert metrics["megapixels"] == pytest.approx(4.8, abs=0.1)


def test_measure_reports_clean_metrics_for_clean_image(clean_image):
    metrics, _ = pixel_metrics.measure(clean_image)

    # A mid-tone gradient with grain should not clip at either end.
    assert metrics["clipped_highlight_ratio"] < 0.001
    assert metrics["crushed_shadow_ratio"] < 0.001
    # And it should carry a real noise floor, not a synthetic zero.
    assert metrics["noise_sigma"] > 0.5


def test_measure_handles_missing_file(tmp_path):
    metrics, image = pixel_metrics.measure(tmp_path / "nope.jpg")

    assert image is None
    assert metrics["megapixels"] == 0.0


# --------------------------------------------------------------------------- #
# Threshold sensitivity
# --------------------------------------------------------------------------- #

def test_lower_threshold_accepts_a_marginal_image(tmp_path):
    image = _noisy_gradient()
    image[200:1200, 200:1600] = 255  # moderately blown
    path = _write(tmp_path / "marginal.jpg", image)

    strict = AcceptanceConfig(threshold=0.95)
    lenient = AcceptanceConfig(threshold=0.30)

    assert score_image(path, config=strict).passed is False
    assert score_image(path, config=lenient).passed is True


def test_config_reads_threshold_from_settings(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "ACCEPTANCE_THRESHOLD", 0.62)
    config = AcceptanceConfig.from_settings()

    assert config.threshold == pytest.approx(0.62)


# --------------------------------------------------------------------------- #
# Aggregation guarantees
# --------------------------------------------------------------------------- #

def test_one_failing_criterion_cannot_be_averaged_away(tmp_path, config):
    """A plain weighted mean would hide a badly failing dimension.

    This is the exact regression that motivated the worst-component ceiling: a
    heavily blown image scored 83% because four healthy dimensions outvoted the
    one that actually mattered.
    """
    image = _noisy_gradient()
    # Blow out ~29% of the frame - far past any tolerance.
    image[200:1400, 200:1600] = 255
    path = _write(tmp_path / "blown.jpg", image)

    report = score_image(path, config=config)

    assert HIGHLIGHTS_CLIPPED in {issue.code for issue in report.issues}
    assert report.passed is False
    assert report.score < config.threshold


def test_critical_issue_is_disqualifying_at_any_score(tmp_path, config):
    """A suspected logo or a sub-4MP frame must fail regardless of the total."""
    small = _noisy_gradient(width=800, height=600)
    path = _write(tmp_path / "small.jpg", small)

    report = score_image(path, config=config)

    assert LOW_RESOLUTION in {issue.code for issue in report.issues}
    assert report.passed is False
    # The number must agree with the verdict rather than showing 90% + "fail".
    assert report.score < config.threshold


def test_critical_semantic_flag_blocks_a_pixel_perfect_image(tmp_path, config):
    """Pixels can look flawless while the model spots a brand logo."""
    path = _write(tmp_path / "clean.jpg", _noisy_gradient())

    report = score_image(
        path,
        config=config,
        semantic={"confidence_score": 0.98, "flags": ["fake brand logo on the shirt"]},
    )

    assert POSSIBLE_IP in {issue.code for issue in report.issues}
    assert report.passed is False


def test_low_semantic_confidence_alone_blocks(tmp_path, config):
    """A low score with no explicit flag still has to stop the image."""
    path = _write(tmp_path / "clean.jpg", _noisy_gradient())

    report = score_image(
        path,
        config=config,
        semantic={"confidence_score": 0.30, "flags": []},
    )

    assert SEMANTIC_FLAGGED in {issue.code for issue in report.issues}
    assert report.passed is False


def test_sub_scores_expose_their_components(clean_image, config):
    """The ceiling reads individual components, so they must be populated."""
    report = score_image(clean_image, config=config)

    for sub in report.sub_scores.values():
        assert sub.components, f"{sub.key} exposed no components"
        assert sub.worst_component == pytest.approx(min(sub.components))


def test_round_trip_preserves_components(clean_image, config):
    from services.acceptance.types import AcceptanceReport

    report = score_image(clean_image, config=config)
    restored = AcceptanceReport.from_dict(report.to_dict())

    for key, sub in report.sub_scores.items():
        assert restored.sub_scores[key].components == pytest.approx(sub.components)
