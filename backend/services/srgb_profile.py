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

    ``ImageCmsProfile.tobytes()`` is the serialisation entry point. An earlier
    version called ``ImageCmsProfile.save()``, which does not exist on
    ``ImageCmsProfile`` - the resulting ``AttributeError`` was caught by the
    broad handler below and turned into a permanent ``None``, so every export
    was silently written untagged. The profile is re-opened after building to
    prove the bytes are a usable ICC profile rather than returning garbage.
    """
    try:
        profile = ImageCms.createProfile("sRGB", colorTemp=6500)
        data = ImageCms.ImageCmsProfile(profile).tobytes()
        # Round-trip so a malformed payload is caught here rather than producing
        # a JPEG that Adobe cannot interpret.
        ImageCms.getOpenProfile(io.BytesIO(data))
        return data
    except Exception:  # noqa: BLE001 - a missing profile must not break export
        logger.exception("Could not build an sRGB ICC profile; exports will be untagged")
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
                # NOTE: ``optimize=True`` is deliberately NOT used here.
                # libjpeg's entropy optimiser aborts with "broken data stream
                # when writing image file" on high-entropy input when combined
                # with 4:4:4 (measured: every detailed 400x400 image failed,
                # while a flat fill succeeded). Because that OSError was caught
                # by the handler below, the export silently returned False and
                # no file was written at all - so every refine/upscale pass on a
                # real photograph failed without an error surfacing.
                # See tests/test_srgb_profile.py::test_detailed_image_exports_successfully.
            )
        return True
    except Exception:  # noqa: BLE001 - disk/encoder errors must not crash a batch
        logger.exception("Failed to write sRGB JPEG %s", path)
        return False


def has_srgb_profile(path: Path | str) -> bool:
    """True when the file carries an sRGB ICC profile.

    The profile is *parsed* rather than byte-searched. An earlier version
    lowercased the raw ICC bytes and looked for ``b"srgb"``, which never
    matches: the description lives in a ``desc`` tag whose text is UTF-16BE
    encoded, so ``"sRGB built-in"`` is not present as ASCII anywhere in the
    stream. That made the check report False for a correctly tagged file.
    """
    try:
        with Image.open(str(path)) as image:
            icc = image.info.get("icc_profile")
    except Exception:  # noqa: BLE001
        return False

    if not icc:
        return False

    # A profile we generated ourselves is sRGB by construction; an exact match
    # avoids depending on how the description happens to be tagged.
    if icc == srgb_profile_bytes():
        return True

    try:
        profile = ImageCms.getOpenProfile(io.BytesIO(icc))
        description = ImageCms.getProfileDescription(profile).lower()
    except Exception:  # noqa: BLE001 - an unparseable profile is not sRGB
        # Some encoders store the description as plain ASCII instead.
        return b"srgb" in icc.lower() or b"iec61966" in icc.lower()

    return "srgb" in description or "iec61966" in description


# --------------------------------------------------------------------------- #
# Standalone embedding — the `embed_srgb` pipeline step
# --------------------------------------------------------------------------- #

#: The marker payload prefix every APP2 ICC segment carries (ICC.1:2010 §7.1).
_ICC_MARKER = b"ICC_PROFILE\x00"

#: Largest ICC chunk that fits a JPEG segment: 65533 payload bytes minus the
#: 12-byte marker and the 2 sequence bytes. The sRGB profile is ~3 KB, so this
#: is one segment in practice; the loop keeps foreign profiles working.
_JPEG_ICC_CHUNK = 65533 - 14


def _inject_icc_jpeg(source: Path, destination: Path, icc: bytes) -> bool:
    """Insert an ICC profile into a JPEG **without re-encoding its pixels**.

    An APP2 segment is written straight after SOI, so the image data is copied
    byte-for-byte — the step can run on a finished export without costing a
    generation of JPEG quality loss, which matters because everything upstream
    (upscale, pure white) already re-encoded once.

    Returns False when the input is not a JPEG or the profile will not fit, in
    which case the caller falls back to a Pillow re-encode.
    """
    try:
        data = source.read_bytes()
    except OSError:
        return False
    if len(data) < 2 or data[:2] != b"\xff\xd8":
        return False

    chunks = [icc[i : i + _JPEG_ICC_CHUNK] for i in range(0, len(icc), _JPEG_ICC_CHUNK)]
    if not chunks:
        return False
    chunks = chunks[:255]  # the sequence numbers are one byte each
    total = len(chunks)

    segments = bytearray()
    for index, chunk in enumerate(chunks, start=1):
        payload = _ICC_MARKER + bytes((index, total)) + chunk
        segments += b"\xff\xe2"
        segments += (len(payload) + 2).to_bytes(2, "big")
        segments += payload

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # SOI, then our APP2 segments, then the file untouched from byte 2 on.
        destination.write_bytes(bytes(data[:2]) + bytes(segments) + data[2:])
    except OSError:
        logger.exception("Could not write ICC-tagged JPEG %s", destination)
        return False
    return has_srgb_profile(destination)


def _reencode_with_profile(source: Path, destination: Path, quality: int) -> bool:
    """Pillow re-encode carrying the profile — the universal fallback.

    Lossy for JPEG (it re-encodes), so it only runs when the lossless APP2
    injection could not; lossless for PNG, where it also preserves alpha.
    """
    profile = srgb_profile_bytes()
    if profile is None:
        return False
    try:
        with Image.open(str(source)) as image:
            kwargs: dict = {"icc_profile": profile}
            fmt = (image.format or "").upper()
            if fmt == "JPEG":
                image.load()
                kwargs.update(quality=int(quality), subsampling=0)
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(str(destination), format=fmt or None, **kwargs)
    except Exception:  # noqa: BLE001 - one bad file must not stop the batch
        logger.exception("Could not re-encode %s with an sRGB profile", source)
        return False
    return has_srgb_profile(destination)


def ensure_srgb_profile(
    source: Path | str,
    destination: Path | str,
    *,
    quality: int = 95,
) -> dict:
    """Make sure the image at ``destination`` (or ``source``) carries sRGB.

    The step's contract, shaped like :func:`pure_white.ensure_pure_white` so
    the runner reads the same keys:

    * already tagged → ``ok, verified`` with no rewrite (a second pass must not
      cost a JPEG generation);
    * JPEG → lossless APP2 injection, Pillow re-encode only as a fallback;
    * PNG (incl. transparent) → Pillow re-save, alpha untouched;
    * unreadable input or no profile bytes → ``ok: False`` with a reason, never
      an exception.

    Returns ``{ok, verified, applied, reason, output_path}``.
    """
    src = Path(source)
    dst = Path(destination)
    if not src.is_file():
        return {"ok": False, "reason": f"Source not found: {src.name}."}

    profile = srgb_profile_bytes()
    if profile is None:
        return {"ok": False, "reason": "The sRGB profile could not be built."}

    if has_srgb_profile(src):
        return {
            "ok": True,
            "verified": True,
            "applied": False,
            "reason": "Already carries an sRGB profile.",
            "output_path": "",
        }

    suffix = src.suffix.lower()
    applied = (
        _inject_icc_jpeg(src, dst, profile)
        if suffix in (".jpg", ".jpeg")
        else _reencode_with_profile(src, dst, quality)
    )
    if not applied and suffix in (".jpg", ".jpeg"):
        # The lossless path failed (malformed table, over-long profile): a
        # re-encode still delivers a tagged file, which is the point of the
        # step — an untagged export is a documented Adobe refusal reason.
        applied = _reencode_with_profile(src, dst, quality)

    if not applied:
        return {"ok": False, "reason": "The sRGB profile could not be embedded."}
    return {
        "ok": True,
        "verified": True,
        "applied": True,
        "reason": "Embedded the sRGB ICC profile.",
        "output_path": str(dst),
    }
