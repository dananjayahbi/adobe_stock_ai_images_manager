"""Tests for the Collector's PNG -> JPEG normalisation.

The behaviour under test is the part that is easy to get subtly wrong: alpha
handling, the absence of chroma subsampling, and never mutating the original.
A conversion that is merely "a JPEG came out" would still pass a naive test
while producing a file with a black halo or invented colour fringing.
"""

import io

import numpy as np
import pytest
from PIL import Image

from services import image_normalizer


def _write_png(path, size=(64, 64), mode="RGB", color=(200, 120, 60)):
    image = Image.new(mode, size, color)
    image.save(path, "PNG")
    return path


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", ["photo.png", "PHOTO.PNG", "graphic.PnG"])
def test_png_files_are_flagged_for_conversion(tmp_path, name):
    path = _write_png(tmp_path / name)

    assert image_normalizer.needs_conversion(path) is True


@pytest.mark.parametrize("name", ["photo.jpg", "photo.jpeg", "notes.txt"])
def test_non_png_files_are_left_alone(tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"not an image")

    assert image_normalizer.needs_conversion(path) is False


# --------------------------------------------------------------------------- #
# Conversion
# --------------------------------------------------------------------------- #

def test_png_is_converted_to_a_readable_jpeg(tmp_path):
    source = _write_png(tmp_path / "in.png", size=(120, 90))
    out_dir = tmp_path / "converted"

    result = image_normalizer.convert_png_to_jpeg(source, out_dir, "rec-1")

    assert result.converted is True
    output = out_dir / "rec-1.jpg"
    assert output.is_file()
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.size == (120, 90)
    assert result.width == 120 and result.height == 90


def test_conversion_leaves_the_original_untouched(tmp_path):
    source = _write_png(tmp_path / "in.png")
    before = source.read_bytes()

    image_normalizer.convert_png_to_jpeg(source, tmp_path / "converted", "rec-2")

    assert source.read_bytes() == before
    assert source.suffix == ".png"


def test_rgba_transparency_is_composited_onto_white(tmp_path):
    """Flattening onto black would turn a soft cut-out into a black halo."""
    source = tmp_path / "alpha.png"
    image = Image.new("RGBA", (40, 40), (255, 0, 0, 0))  # fully transparent red
    image.save(source, "PNG")

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-3"
    )

    assert result.converted is True
    with Image.open(result.output_path) as converted:
        pixels = np.asarray(converted.convert("RGB"))
    # Every pixel should be white, not black.
    assert pixels.min() > 240, f"transparent area rendered as {pixels.min()}"


def test_palette_png_with_transparency_is_handled(tmp_path):
    source = tmp_path / "palette.png"
    image = Image.new("P", (32, 32), 0)
    image.info["transparency"] = 0
    image.save(source, "PNG")

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-4"
    )

    assert result.converted is True
    with Image.open(result.output_path) as converted:
        assert converted.mode == "RGB"


def test_greyscale_png_is_converted(tmp_path):
    source = _write_png(tmp_path / "grey.png", mode="L", color=128)

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-5"
    )

    assert result.converted is True
    with Image.open(result.output_path) as converted:
        assert converted.mode == "RGB"


def test_conversion_disables_chroma_subsampling(tmp_path):
    """4:2:0 would smear saturated single-pixel detail into colour fringing.

    The sampling factors are read directly rather than inferred from the pixel
    values: a subsampled JPEG of this pattern still decodes to roughly the
    right colours, so only the encoded factors prove 4:4:4 was requested.
    Pillow exposes them as ``layer``; the first entry is the Y component, whose
    (h, v) sampling factors are (1, 1) only when no subsampling is applied.
    """
    source = tmp_path / "detail.png"
    image = Image.new("RGB", (64, 64), (255, 0, 0))
    # Alternating single-pixel colour columns: the pattern 4:2:0 destroys.
    pixels = image.load()
    for y in range(64):
        for x in range(0, 64, 2):
            pixels[x, y] = (0, 0, 255)
    image.save(source, "PNG")

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-6"
    )

    with Image.open(result.output_path) as converted:
        converted.load()
        luma_sampling = converted.layer[0]
    assert luma_sampling[:2] == (1, 1), (
        f"chroma subsampling was applied: Y sampling factors {luma_sampling[:2]}"
    )


def test_detailed_image_converts_successfully(tmp_path):
    """A high-entropy image must convert, not silently fail.

    Regression guard: ``optimize=True`` together with 4:4:4 makes libjpeg abort
    with "broken data stream when writing image file" on detailed input. The
    error is swallowed by the caller's handler, so the only symptom is that no
    file appears - which is exactly what a real AI render looks like.
    """
    source = tmp_path / "detailed.png"
    rng = np.random.default_rng(11)
    noisy = rng.integers(0, 255, (400, 400, 3), dtype=np.uint8)
    Image.fromarray(noisy, "RGB").save(source, "PNG")

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-12", quality=100
    )

    assert result.converted is True, result.reason
    assert (tmp_path / "converted" / "rec-12.jpg").is_file()


def test_conversion_is_idempotent_for_the_same_record_id(tmp_path):
    source = _write_png(tmp_path / "in.png")
    out_dir = tmp_path / "converted"

    image_normalizer.convert_png_to_jpeg(source, out_dir, "rec-7")
    image_normalizer.convert_png_to_jpeg(source, out_dir, "rec-7")

    assert len(list(out_dir.glob("*.jpg"))) == 1


def test_quality_is_configurable(tmp_path):
    """A lower quality must actually produce a smaller file."""
    source = tmp_path / "photo.png"
    rng = np.random.default_rng(7)
    noisy = rng.integers(0, 255, (200, 200, 3), dtype=np.uint8)
    Image.fromarray(noisy, "RGB").save(source, "PNG")

    high = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "hi", "rec-8", quality=100
    )
    low = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "lo", "rec-8", quality=40
    )

    assert high.converted is True, high.reason
    assert low.converted is True, low.reason
    high_size = (tmp_path / "hi" / "rec-8.jpg").stat().st_size
    low_size = (tmp_path / "lo" / "rec-8.jpg").stat().st_size
    assert low_size < high_size, f"quality=40 gave {low_size}B vs quality=100 {high_size}B"


# --------------------------------------------------------------------------- #
# Failure handling
# --------------------------------------------------------------------------- #

def test_missing_file_reports_a_reason_instead_of_raising(tmp_path):
    result = image_normalizer.convert_png_to_jpeg(
        tmp_path / "nope.png", tmp_path / "converted", "rec-9"
    )

    assert result.converted is False
    assert result.output_path is None
    assert result.reason


def test_undecodable_file_reports_a_reason_instead_of_raising(tmp_path):
    source = tmp_path / "broken.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n not really a png")

    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-10"
    )

    assert result.converted is False
    assert result.reason


def test_result_serialises_for_the_stage_detail_blob(tmp_path):
    source = _write_png(tmp_path / "in.png")
    result = image_normalizer.convert_png_to_jpeg(
        source, tmp_path / "converted", "rec-11"
    )

    payload = result.to_dict()
    assert payload["converted"] is True
    assert set(payload) == {
        "converted",
        "output_path",
        "source_suffix",
        "width",
        "height",
        "reason",
    }
