"""PNG -> JPEG normalisation for the Collector stage.

Why this runs automatically
---------------------------
Adobe Stock accepts **JPEG only** for photos; a PNG submission is refused on
format grounds regardless of how good the image is. Meanwhile most generative
tools emit PNG. Refusing the upload at the door therefore rejects images that
would be perfectly acceptable one conversion later.

So the Collector accepts PNG and immediately writes a JPEG at **quality 100**
next to the original. The record's working copy becomes that JPEG, and the
uploaded original is left untouched in the inbox as the authoritative audit
source - nothing is destructive.

Two details that matter
-----------------------
* **Alpha.** A PNG's alpha channel has no meaning in a JPEG. Flattening onto
  black would turn a soft cut-out into a hard black halo, so transparency is
  composited onto **white** instead.
* **Chroma.** Subsampling is disabled (4:4:4). AI output often has saturated
  single-pixel detail, and 4:2:0 would smear it into exactly the colour
  fringing the acceptance scorer flags - the conversion must not manufacture a
  defect that the pipeline then has to repair.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

#: PNG files are the only format this stage rewrites.
PNG_SUFFIXES = frozenset({".png"})


@dataclass
class ConversionResult:
    """Outcome of one normalisation attempt."""

    #: True when a JPEG was written.
    converted: bool
    #: Path of the written JPEG, or None when nothing was produced.
    output_path: str | None = None
    source_suffix: str = ""
    width: int | None = None
    height: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "converted": self.converted,
            "output_path": self.output_path,
            "source_suffix": self.source_suffix,
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
        }


def needs_conversion(path: str | Path, cfg: Settings | None = None) -> bool:
    """True when this file is a PNG the Collector should rewrite."""
    suffixes = getattr(cfg or default_settings, "PNG_EXTENSIONS", PNG_SUFFIXES)
    return Path(path).suffix.lower() in {s.lower() for s in suffixes}


def _flatten(image: Image.Image) -> Image.Image:
    """Convert any PNG mode to RGB, compositing transparency onto white.

    ``P`` mode images may carry transparency in their palette, so they are
    expanded through RGBA first; converting them straight to RGB would silently
    substitute the palette's index-0 colour for every transparent pixel.
    """
    if image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    ):
        rgba = image.convert("RGBA")
        canvas = Image.new("RGB", rgba.size, (255, 255, 255))
        canvas.paste(rgba, mask=rgba.split()[-1])
        return canvas
    if image.mode != "RGB":
        return image.convert("RGB")
    return image


def convert_png_to_jpeg(
    source: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    quality: int | None = None,
) -> ConversionResult:
    """Write ``{output_dir}/{record_id}.jpg`` from a PNG source.

    Args:
        source: The uploaded PNG (never modified).
        output_dir: Directory that receives the JPEG.
        record_id: Names the output deterministically, so a re-run overwrites
            rather than accumulating copies.
        quality: JPEG quality; defaults to ``settings.PNG_CONVERSION_QUALITY``.

    Returns:
        A :class:`ConversionResult`. ``converted`` is False - with a reason -
        when the file could not be decoded, so the caller can keep the record
        moving on its original rather than failing the batch.
    """
    cfg = default_settings
    resolved_quality = int(
        quality if quality is not None else getattr(cfg, "PNG_CONVERSION_QUALITY", 100)
    )

    src = Path(source)
    if not src.is_file():
        return ConversionResult(False, source_suffix=src.suffix, reason="File not found.")

    destination = Path(output_dir) / f"{record_id}.jpg"
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as image:
            width, height = image.size
            rgb = _flatten(image)
            rgb.save(
                destination,
                format="JPEG",
                quality=resolved_quality,
                subsampling=0,  # 4:4:4 - do not invent colour fringing
                # ``optimize`` is intentionally omitted: libjpeg's optimiser
                # fails with "broken data stream" on high-entropy images at
                # 4:4:4, which would silently reject exactly the detailed
                # renders this stage exists to convert. See
                # tests/test_image_normalizer.py::test_detailed_image_converts_successfully.
            )
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop a batch
        logger.exception("PNG conversion failed for %s", src)
        return ConversionResult(
            False, source_suffix=src.suffix, reason=f"{type(exc).__name__}: {exc}"
        )

    return ConversionResult(
        converted=True,
        output_path=str(destination),
        source_suffix=src.suffix,
        width=width,
        height=height,
        reason="Converted PNG to JPEG at quality 100 for Adobe Stock.",
    )
