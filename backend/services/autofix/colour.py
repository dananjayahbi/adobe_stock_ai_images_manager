"""Colour-space conversion helpers for the auto-fix engine.

Adobe requires an *embedded* sRGB profile. Two different situations both
surface as the ``not_srgb`` issue code, and they need different treatment:

* **Untagged file** - pixels are almost certainly already sRGB, so tagging them
  is enough. Re-encoding is lossless in intent.
* **Wrong profile** (Adobe RGB, Display P3, ...) - the pixel *numbers* are in a
  different space, so simply tagging them sRGB would actively corrupt the
  colours. The pixels must be transformed through the source profile first.

Only LittleCMS (via Pillow's ``ImageCms``) can do the second case, which is why
this module exists separately from :mod:`services.srgb_profile` - that module
*writes* a profile, this one *interprets* one.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

from services.srgb_profile import has_srgb_profile

logger = logging.getLogger(__name__)


@dataclass
class ColourConversion:
    """Outcome of preparing an image's pixels for sRGB export."""

    image_rgb: np.ndarray
    #: True when the pixels were transformed through a non-sRGB profile.
    transformed: bool
    #: True when the source carried a profile that was not sRGB.
    had_foreign_profile: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "transformed": self.transformed,
            "had_foreign_profile": self.had_foreign_profile,
            "reason": self.reason,
        }


def _load_rgb(path: Path) -> tuple[np.ndarray | None, bytes | None]:
    """Decode a file to an RGB array plus its raw ICC bytes, if any."""
    try:
        with Image.open(str(path)) as image:
            icc = image.info.get("icc_profile")
            rgb = image.convert("RGB")
            return np.asarray(rgb, dtype=np.uint8), (icc or None)
    except Exception:  # noqa: BLE001 - a corrupt file must not crash a batch
        logger.exception("Could not decode %s for colour conversion", path)
        return None, None


def convert_to_srgb(path: Path | str) -> ColourConversion | None:
    """Return ``path``'s pixels converted into the sRGB colour space.

    Untagged files are returned unchanged (they are already interpreted as
    sRGB by every consumer), a non-sRGB profile is transformed through
    LittleCMS, and an already-sRGB file is passed straight through.

    Returns None when the file cannot be decoded.
    """
    source = Path(path)
    rgb, icc = _load_rgb(source)
    if rgb is None:
        return None

    if not icc:
        return ColourConversion(
            rgb,
            transformed=False,
            had_foreign_profile=False,
            reason="No ICC profile present; pixels are already interpreted as sRGB.",
        )

    if has_srgb_profile(source):
        return ColourConversion(
            rgb,
            transformed=False,
            had_foreign_profile=False,
            reason="File already carries an sRGB profile.",
        )

    # A profile exists and it is not sRGB: the pixel numbers mean something
    # else, so they must be mapped rather than merely re-tagged.
    try:
        source_profile = ImageCms.getOpenProfile(io.BytesIO(icc))
        target_profile = ImageCms.createProfile("sRGB", colorTemp=6500)
        description = ImageCms.getProfileDescription(source_profile).strip()

        with Image.fromarray(rgb, mode="RGB") as pil_image:
            converted = ImageCms.profileToProfile(
                pil_image,
                source_profile,
                target_profile,
                renderingIntent=ImageCms.Intent.PERCEPTUAL,
                outputMode="RGB",
            )
            transformed = np.asarray(converted, dtype=np.uint8)
            converted.close()

        return ColourConversion(
            transformed,
            transformed=True,
            had_foreign_profile=True,
            reason=f"Converted from '{description}' to sRGB IEC61966-2.1.",
        )
    except Exception as exc:  # noqa: BLE001 - fall back rather than fail the run
        logger.exception("ICC transform failed for %s", source)
        return ColourConversion(
            rgb,
            transformed=False,
            had_foreign_profile=True,
            reason=(
                "Could not interpret the embedded profile "
                f"({exc}); pixels were re-tagged as sRGB without conversion."
            ),
        )
