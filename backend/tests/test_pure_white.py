"""Tests for the pure-white verification/clamp step.

The defect this guards: a "background" at RGB 250 *looks* white but is not
`#FFFFFF`, and a naive global clamp blows out specular highlights on the
subject. The border check must gate the clamp, and the clamp must respect
region connectivity when protection is on.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from services import pure_white


def _write(path, array: np.ndarray) -> None:
    Image.fromarray(array, mode="RGB").save(path, "PNG")


def _image(height: int, width: int, color: tuple[int, int, int]) -> np.ndarray:
    return np.full((height, width, 3), color, dtype=np.uint8)


class TestBorderCheck:
    def test_near_white_border_passes(self):
        image = _image(64, 64, (250, 250, 250))
        near_white, means = pure_white.border_is_near_white(image)
        assert near_white is True
        assert means == [250, 250, 250]

    def test_coloured_border_is_rejected(self):
        # Arrays are BGR, matching cv2.imread's contract (what the step reads).
        image = _image(64, 64, (30, 30, 200))  # BGR = red-dominant
        near_white, means = pure_white.border_is_near_white(image)
        assert near_white is False
        assert means == [200, 30, 30]  # reported as RGB

    def test_white_subject_on_grey_background_still_rejected(self):
        """The border samples the *frame* — a white object inside does not
        make a grey backdrop count as white."""
        image = _image(64, 64, (120, 120, 120))
        image[16:48, 16:48] = 255
        assert pure_white.border_is_near_white(image)[0] is False

    def test_border_min_is_configurable(self):
        image = _image(64, 64, (246, 246, 246))
        assert pure_white.border_is_near_white(image, border_min=248)[0] is False
        assert pure_white.border_is_near_white(image, border_min=244)[0] is True


class TestClamp:
    def test_near_white_background_becomes_pure_white(self):
        image = _image(64, 64, (250, 250, 250))
        clamped, changed = pure_white.clamp_background(image, threshold=245)
        assert changed == 64 * 64
        assert int(clamped.min()) == 255

    def test_pixels_at_or_below_threshold_are_untouched(self):
        image = _image(32, 32, (245, 245, 245))  # not > threshold
        clamped, changed = pure_white.clamp_background(image, threshold=245)
        assert changed == 0
        assert int(clamped.max()) == 245

    def test_protect_subject_preserves_enclosed_highlights(self):
        """A bright specular blob inside a dark subject must NOT be clamped,
        because it is not connected to the border."""
        image = _image(64, 64, (250, 250, 250))  # near-white background
        image[16:48, 16:48] = (40, 40, 40)  # dark subject
        image[28:36, 28:36] = (250, 250, 250)  # specular highlight on subject

        clamped, _ = pure_white.clamp_background(image, threshold=245, protect_subject=True)
        # Background went pure...
        assert int(clamped[0, 0, 0]) == 255
        # ...the enclosed highlight did not.
        assert int(clamped[32, 32, 0]) == 250

    def test_no_protection_clamps_everything_above_threshold(self):
        image = _image(64, 64, (10, 10, 10))
        image[28:36, 28:36] = (250, 250, 250)
        clamped, changed = pure_white.clamp_background(
            image, threshold=245, protect_subject=False
        )
        assert changed == 64
        assert int(clamped[32, 32, 0]) == 255


class TestEnsurePureWhite:
    def test_near_white_image_is_clamped_and_written(self, tmp_path):
        source = tmp_path / "src.png"
        destination = tmp_path / "out.jpg"
        _write(source, _image(64, 64, (251, 251, 251)))

        result = pure_white.ensure_pure_white(source, destination)

        assert result["ok"] is True
        assert result["verified"] is True
        assert result["applied"] is True
        assert result["clamped_pixels"] == 64 * 64
        assert destination.exists()

        written = np.asarray(Image.open(destination).convert("RGB"))
        assert int(written.min()) == 255  # mathematically pure white

    def test_coloured_background_is_verified_false_and_not_written(self, tmp_path):
        source = tmp_path / "src.png"
        destination = tmp_path / "out.jpg"
        _write(source, _image(64, 64, (180, 40, 40)))

        result = pure_white.ensure_pure_white(source, destination)

        assert result["ok"] is True
        assert result["verified"] is False
        assert result["applied"] is False
        assert not destination.exists()
        assert "not near-white" in result["reason"]

    def test_already_pure_white_reports_verified_without_a_rewrite(self, tmp_path):
        source = tmp_path / "src.png"
        destination = tmp_path / "out.jpg"
        _write(source, _image(64, 64, (255, 255, 255)))

        result = pure_white.ensure_pure_white(source, destination)

        assert result["ok"] is True
        assert result["verified"] is True
        assert result["applied"] is False  # nothing changed
        assert not destination.exists()

    def test_undecodable_file_is_a_reportable_failure(self, tmp_path):
        source = tmp_path / "broken.png"
        source.write_bytes(b"not an image")

        result = pure_white.ensure_pure_white(source, tmp_path / "out.jpg")

        assert result["ok"] is False
        assert "Could not read" in result["reason"]


class TestCatalogIntegration:
    def test_default_config_matches_the_service_defaults(self):
        from services import pipeline_defs

        config = pipeline_defs.default_step_config("pure_white")
        assert config["threshold"] == pure_white.DEFAULT_THRESHOLD
        assert config["border_min"] == pure_white.DEFAULT_BORDER_MIN
        assert config["protect_subject"] is True

    def test_pure_white_is_picked_by_raster_only(self):
        from services import pipeline_defs

        assert "pure_white" in pipeline_defs.available_steps("raster")
        assert "pure_white" not in pipeline_defs.available_steps("png")

    def test_pure_white_sits_after_qc_and_before_metadata(self):
        """Order matters: clamping before Acceptance QC would game the exposure
        score (a clamped background reads as clipped highlights)."""
        from services import pipeline_defs

        order = list(pipeline_defs.STEP_ORDER)
        assert order.index("compatibility") < order.index("pure_white")
        assert order.index("pure_white") < order.index("metadata")
