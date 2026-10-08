"""Alpha-channel helpers for PNG batches (batch pipeline v2).

The raster pipeline never sees transparency (PNGs are flattened to JPEG at the
Collector). A PNG batch is the opposite: alpha *is* the deliverable, so every
helper here preserves it and only ever writes PNG.

Provided:
* ``has_alpha``        - cheap probe before treating a file as a cut-out.
* ``white_thumbnail``  - 400px JPEG thumbnail with alpha composited onto white
                         (dropping alpha directly renders transparent pixels as
                         black, which reads as a corrupted thumbnail).
* ``lanczos_rgba``     - alpha-preserving resize used by the PNG upscale path.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (400, 400)


def has_alpha(path: str | Path) -> bool:
    """True when the file is a PNG carrying a non-trivial alpha channel."""
    try:
        with Image.open(path) as img:
            if img.mode not in ("RGBA", "LA", "PA"):
                return False
            alpha = img.getchannel("A")
            lo, hi = alpha.getextrema()
            return lo < hi or lo < 255  # any transparency at all
    except Exception:  # noqa: BLE001 - unreadable input is "no alpha"
        return False


def white_thumbnail(
    source: str | Path,
    thumb_dir: str | Path,
    record_id: str,
) -> str:
    """Write a 400px JPEG thumbnail, compositing transparency onto white.

    Returns the thumbnail path, or ``""`` on failure (mirrors
    ``storage.generate_thumbnail``'s contract).
    """
    out = Path(thumb_dir) / f"thumb_{record_id}.jpg"
    try:
        with Image.open(source) as img:
            rgba = img.convert("RGBA")
            rgba.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            composited = Image.alpha_composite(background, rgba).convert("RGB")
            composited.save(out, "JPEG", quality=85)
        return str(out)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to build PNG thumbnail for %s", source)
        return ""


def lanczos_rgba(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize an RGBA image with Lanczos, keeping the alpha channel intact."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.resize(size, Image.Resampling.LANCZOS)


def upscale_rgba_to_long_edge(source: str | Path, target_long_edge: int) -> Image.Image:
    """Load ``source`` and scale it so its long edge is ``target_long_edge``.

    Upscales and downscale are both handled by Lanczos; callers that need a
    neural pass split the channels first (see ``pipeline_runner``).
    """
    with Image.open(source) as img:
        rgba = img.convert("RGBA")
        width, height = rgba.size
        long_edge = max(width, height)
        if long_edge == target_long_edge or long_edge <= 0:
            return rgba.copy()
        scale = target_long_edge / long_edge
        new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        return lanczos_rgba(rgba, new_size)
