"""Tests for the sRGB detection fix in the acceptance scorer.

A real bug lived here. ``pixel_metrics._icc_is_srgb`` searched the raw ICC bytes
for ``b"srgb"``, but the profile this pipeline *writes* stores its description
in a ``mluc`` tag as UTF-16BE, so the ASCII string is absent. The scorer
therefore reported ``is_srgb = 0.0`` for a correctly tagged file and raised a
spurious "not in the sRGB colour space" issue on every exported image.

These tests pin the behaviour that matters: a file written by our own export
path must score as sRGB.
"""

import numpy as np
import pytest
from PIL import Image, ImageCms

from services.acceptance.pixel_metrics import _container_stats, _icc_is_srgb
from services.srgb_profile import srgb_profile_bytes, write_srgb_jpeg


@pytest.fixture()
def rgb_array() -> np.ndarray:
    rng = np.random.default_rng(seed=7)
    return (rng.random((80, 120, 3)) * 255).astype("uint8")


def test_our_own_profile_has_no_ascii_name():
    """Guards the premise of the fix: a byte search cannot work here.

    If a future Pillow release ever emits an ASCII description, this test fails
    and the byte-search fallback below can be reconsidered.
    """
    data = srgb_profile_bytes()
    assert data, "the sRGB profile must be buildable"
    assert b"srgb" not in data.lower()
    assert b"iec61966" not in data.lower()


def test_icc_is_srgb_accepts_our_profile():
    """The regression: this returned False for our own sRGB profile."""
    assert _icc_is_srgb(srgb_profile_bytes()) is True


def test_icc_is_srgb_rejects_empty_bytes():
    assert _icc_is_srgb(b"") is False


def test_icc_is_srgb_accepts_a_foreign_srgb_profile():
    """A system sRGB profile with a real ASCII description must also pass."""
    import io

    profile = ImageCms.createProfile("sRGB", colorTemp=6500)
    data = ImageCms.ImageCmsProfile(profile).tobytes()
    assert _icc_is_srgb(data) is True
    # Round-trip through BytesIO to mirror how the scorer receives the bytes.
    assert ImageCms.getOpenProfile(io.BytesIO(data)) is not None


def test_exported_file_scores_as_srgb(tmp_path, rgb_array):
    """End-to-end: the export path's output must measure as sRGB."""
    destination = tmp_path / "exported.jpg"
    assert write_srgb_jpeg(rgb_array, destination) is True

    stats = _container_stats(destination)
    assert stats["is_jpeg"] == 1.0
    assert stats["has_icc_profile"] == 1.0
    assert stats["is_srgb"] == 1.0, (
        "a file written by write_srgb_jpeg must be detected as sRGB; "
        "the byte-search implementation reported 0.0 here"
    )


def test_untagged_file_is_treated_as_srgb(tmp_path, rgb_array):
    """An untagged JPEG is the near-universal sRGB convention, not an error."""
    destination = tmp_path / "untagged.jpg"
    Image.fromarray(rgb_array[:, :, ::-1]).save(str(destination), "JPEG", quality=90)

    stats = _container_stats(destination)
    assert stats["has_icc_profile"] == 0.0
    assert stats["is_srgb"] == 1.0
