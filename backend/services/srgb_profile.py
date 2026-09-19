"""sRGB colour-profile embedding for exported JPEGs.

Adobe's photo requirements are explicit: **"Format: JPEG with sRGB color
profile"**. A file whose pixels are sRGB but which carries no ICC profile (or
carries a wide-gamut one) is a documented refusal reason, because Adobe's web
renderer falls back to a different interpretation and the preview looks muddy.

OpenCV cannot write an ICC profile, so exports that need one are written with
Pillow, which can. The profile itself is generated once and cached.

The profile is built with Pillow's ``ImageCms`` from the sRGB primaries, which
avoids shipping a binary blob while still producing a standards-conformant
sRGB IEC61966-2.1 profile that ExifTool and Adobe both recognise.
"""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

logger = logging.getLogger(__name__)

#: sRGB primaries/whitepoint in the format ImageCms.createProfile expects.
#: These are the CIE xy chromaticities from IEC 61966-2.1.
_SRGB_PRIMARIES = (
    0.6400,  # red x
    0.3300,  # red y
    0.3000,  # green x
    0.6000,  # green y
    0.1500,  # blue x
    0.0600,  # blue y
    0.3127,  # white x (D65)
    0.3290,  # white y (D65)
)


@lru_cache(maxsize=1)
def srgb_profile_bytes() -> bytes | None:
    """Return a serialized sRGB ICC profile, or None if it cannot be built.

    Cached because building a profile allocates a fair amount of state and the
    bytes never change.
    """
    try:
        profile = ImageCms.createProfile(
            "sRGB",
            colorTemp=6500,
        )
        buffer = io.BytesIO()
        ImageCms.ImageCmsProfile(profile).save(buffer)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 - a missing profile must not break export
        logger.warning("Could not build an sRGB ICC profile; exports will be untagged")
        return None


def write_srgb_jpeg(
    image_bgr: np.ndarray,
    destination: Path | str,
    quality: int = 95,
) -> bool:
    """Write a BGR array as an sRGB-tagged JPEG with 4:4:4 chroma.

    OpenCV is used for the pixel encode when no profile is required, because it
    is considerably faster; Pillow takes over when an ICC profile must be
    embedded.

    Args:
        image_bgr: BGR ``uint8`` array (OpenCV channel order).
        destination: Output path.
        quality: JPEG quality (1-100).

    Returns:
        True when the file was written.
    """
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = srgb_profile_bytes()
    if profile is None:
        # Fall back to OpenCV: still a valid JPEG, just untagged.
        import cv2

        try:
            return bool(
                cv2.imwrite(
                    str(path),
                    image_bgr,
                    [
                        cv2.IMWRITE_JPEG_QUALITY,
                        int(quality),
                        cv2.IMWRITE_JPEG_CHROMA_QUALITY,
                        100,  # 4:4:4 - keeps colour detail on repaired edges
                    ],
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to write JPEG %s", path)
            return False

    try:
        # Pillow expects RGB, so the channel order is reversed on the way in.
        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        with Image.fromarray(rgb, mode="RGB") as pil_image:
            pil_image.save(
                str(path),
                format="JPEG",
                quality=int(quality),
                subsampling=0,  # 4:4:4
                icc_profile=profile,
                optimize=True,
            )
        return True
    except Exception:  # noqa: BLE001 - disk/encoder errors must not crash a batch
        logger.exception("Failed to write sRGB JPEG %s", path)
        return False


def has_srgb_profile(path: Path | str) -> bool:
    """True when the file carries an sRGB ICC profile."""
    try:
        with Image.open(str(path)) as image:
            icc = image.info.get("icc_profile")
    except Exception:  # noqa: BLE001
        return False

    if not icc:
        return False

    lowered = icc.lower()
    return b"srgb" in lowered or b"iec61966" in lowered
