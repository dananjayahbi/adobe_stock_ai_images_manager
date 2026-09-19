"""sRGB profile embedding and detection.

These tests exist because the module previously had none, and that let two real
defects ship:

1. ``srgb_profile_bytes`` called ``ImageCmsProfile.save()``, which does not
   exist on that class. The ``AttributeError`` was swallowed by a broad
   ``except``, so the profile was *always* ``None`` and every export silently
   fell back to an untagged JPEG.
2. ``has_srgb_profile`` byte-searched the raw ICC stream for ``b"srgb"``. The
   description lives in a ``desc`` tag encoded as UTF-16BE, so a correctly
   tagged file reported ``False``.

Both are asserted directly below so neither can return unnoticed.
"""
from __future__ import annotations

import io
import pathlib

import cv2
import numpy as np
import pytest
from PIL import Image, ImageCms

from services.srgb_profile import (
    has_srgb_profile,
    srgb_profile_bytes,
    write_srgb_jpeg,
)

#: Every conformant ICC profile carries this signature at byte offset 36.
ICC_SIGNATURE = b"acsp"


@pytest.fixture(autouse=True)
def _fresh_profile_cache():
    """Drop the lru_cache so a test cannot inherit another's patched result."""
    srgb_profile_bytes.cache_clear()
    yield
    srgb_profile_bytes.cache_clear()


def _bgr(width: int = 64, height: int = 48) -> np.ndarray:
    """A small BGR gradient, the channel order the encoder expects."""
    x = np.linspace(0, 255, width, dtype=np.uint8)
    gradient = np.tile(x, (height, 1))
    return np.dstack([gradient, np.flipud(gradient), gradient // 2])


# --------------------------------------------------------------------------- #
# Profile construction
# --------------------------------------------------------------------------- #

def test_profile_is_built_and_is_a_real_icc_profile():
    """The regression: this used to return None because of the bad API call."""
    data = srgb_profile_bytes()

    assert data is not None, "the sRGB profile must build; exports depend on it"
    assert len(data) > 100
    assert data[36:40] == ICC_SIGNATURE


def test_profile_round_trips_through_pillow():
    """The bytes must be openable, not merely non-empty."""
    data = srgb_profile_bytes()

    profile = ImageCms.getOpenProfile(io.BytesIO(data))

    assert "srgb" in ImageCms.getProfileDescription(profile).lower()


def test_profile_is_cached():
    """Building a profile is not free, so the result must be reused."""
    first = srgb_profile_bytes()
    second = srgb_profile_bytes()

    assert first is second or first == second


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #

def test_write_embeds_the_profile(tmp_path: pathlib.Path):
    """The end-to-end regression: the file on disk must carry the profile."""
    destination = tmp_path / "out.jpg"

    assert write_srgb_jpeg(_bgr(), destination, quality=95) is True

    with Image.open(destination) as image:
        icc = image.info.get("icc_profile")

    assert icc, "the written JPEG has no ICC profile"
    assert icc[36:40] == ICC_SIGNATURE


def test_write_preserves_channel_order(tmp_path: pathlib.Path):
    """BGR in must become the same colours, not a red/blue swap."""
    destination = tmp_path / "red.jpg"
    bgr = np.zeros((8, 8, 3), dtype=np.uint8)
    bgr[:, :, 2] = 255  # pure red in BGR

    write_srgb_jpeg(bgr, destination, quality=100)

    with Image.open(destination) as image:
        red, green, blue = image.convert("RGB").getpixel((4, 4))

    assert red > 200 and green < 60 and blue < 60


def _chroma_subsampling(path: pathlib.Path) -> tuple[int, ...]:
    """Read the sampling factors from a JPEG's SOF0 frame header.

    Pillow does not expose these, and they are the only way to prove the encoder
    really used 4:4:4 rather than silently averaging colour detail.
    """
    data = path.read_bytes()
    index = 2  # skip SOI
    while index < len(data) - 1:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0xD9):  # SOI / EOI carry no length
            index += 2
            continue
        length = int.from_bytes(data[index + 2:index + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2):  # baseline / extended / progressive SOF
            # SOF: length, precision, height, width, components...
            components = data[index + 9]
            factors = []
            for component in range(components):
                base = index + 10 + component * 3
                factors.append(data[base + 1])
            return tuple(factors)
        index += 2 + length
    raise AssertionError("no SOF marker found")


def test_write_uses_full_chroma_sampling(tmp_path: pathlib.Path):
    """4:4:4 keeps colour detail on repaired edges; 4:2:0 would average it away."""
    destination = tmp_path / "chroma.jpg"

    write_srgb_jpeg(_bgr(), destination, quality=100)

    # 0x11 on every component means no subsampling (4:4:4). 4:2:0 would show a
    # luma factor of 0x22 against 0x11 chroma factors.
    assert _chroma_subsampling(destination) == (0x11, 0x11, 0x11)


def test_write_creates_missing_parent_directories(tmp_path: pathlib.Path):
    destination = tmp_path / "nested" / "deeper" / "out.jpg"

    assert write_srgb_jpeg(_bgr(), destination) is True
    assert destination.is_file()


def test_write_returns_false_when_the_destination_is_unwritable(tmp_path: pathlib.Path):
    """A disk error must be reported, not raised into a batch."""
    directory = tmp_path / "as-directory"
    directory.mkdir()

    assert write_srgb_jpeg(_bgr(), directory) is False


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

def test_detects_the_profile_it_wrote(tmp_path: pathlib.Path):
    """The second regression: this reported False for a tagged file."""
    destination = tmp_path / "tagged.jpg"
    write_srgb_jpeg(_bgr(), destination)

    assert has_srgb_profile(destination) is True


def test_rejects_an_untagged_jpeg(tmp_path: pathlib.Path):
    """OpenCV cannot write an ICC profile, so this file is genuinely untagged."""
    destination = tmp_path / "untagged.jpg"
    cv2.imwrite(str(destination), _bgr(), [cv2.IMWRITE_JPEG_QUALITY, 95])

    assert has_srgb_profile(destination) is False


def test_rejects_a_missing_file(tmp_path: pathlib.Path):
    assert has_srgb_profile(tmp_path / "absent.jpg") is False


def test_rejects_a_non_image(tmp_path: pathlib.Path):
    text = tmp_path / "not-an-image.jpg"
    text.write_text("plain text, not a JPEG", encoding="utf-8")

    assert has_srgb_profile(text) is False


def test_accepts_an_externally_tagged_profile(tmp_path: pathlib.Path):
    """A profile built elsewhere must be recognised, not just our own bytes.

    This is the branch that matters: our own profile has no plain-ASCII name
    (Pillow stores it as ``sRGB built-in`` in an ``mluc`` tag), so an exact byte
    comparison would not be enough for a profile produced by another tool. The
    Windows sRGB profile is a genuinely different 3144-byte profile whose
    description is ``sRGB IEC61966-2.1``.
    """
    foreign_path = next(
        (
            candidate
            for candidate in (
                pathlib.Path(r"C:\Windows\System32\spool\drivers\color\sRGB Color Space Profile.icm"),
                pathlib.Path("/usr/share/color/icc/colord/sRGB.icc"),
                pathlib.Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc"),
            )
            if candidate.is_file()
        ),
        None,
    )
    if foreign_path is None:
        pytest.skip("no system sRGB profile available to test the parse branch")

    foreign = foreign_path.read_bytes()
    assert foreign != srgb_profile_bytes(), "expected a profile distinct from ours"

    destination = tmp_path / "external.jpg"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8), mode="RGB").save(
        destination, format="JPEG", icc_profile=foreign
    )

    assert has_srgb_profile(destination) is True


def test_rejects_a_non_srgb_profile(tmp_path: pathlib.Path):
    """Detection must not answer True for any profile at all."""
    foreign_path = pathlib.Path(r"C:\Windows\System32\spool\drivers\color\RSWOP.icm")
    if not foreign_path.is_file():
        pytest.skip("no non-sRGB system profile available")

    destination = tmp_path / "cmyk-ish.jpg"
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8), mode="RGB").save(
        destination, format="JPEG", icc_profile=foreign_path.read_bytes()
    )

    assert has_srgb_profile(destination) is False
