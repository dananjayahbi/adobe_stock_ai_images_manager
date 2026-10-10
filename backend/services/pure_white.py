"""Pure-white background verification and clamping (Adobe Stock review aid).

Adobe reviewers expect images sold on a white background to sit on a
mathematically pure ``#FFFFFF``. AI-generated and re-compressed images often
land at 248-254 instead - close enough to look white, but not *pure* white,
and a hairline of near-white can read as an untidy edge at 100% zoom.

The algorithm mirrors the research recommendation:

1. **Verify the border.** Sample a thin frame around the outer edge. Only if
   every channel averages at least ``border_min`` (default 248) is the
   background considered near-white - anything else is a coloured/dark
   background and is left untouched (the step reports *skipped*, never fails).
2. **Clamp gently.** Pixels above ``threshold`` (default 245) become exactly
   255. With ``protect_subject`` the clamp is restricted to the region
   *connected to the border*, so specular highlights on the subject - bright
   but enclosed by darker pixels - are never blown out.

The result is written as an sRGB-tagged JPEG (Adobe requires JPEG + embedded
sRGB for photos); a second JPEG encode can ring a pixel or two around a hard
silhouette, but the flat background - the part reviewers check - stays 255.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from services.srgb_profile import write_srgb_jpeg

logger = logging.getLogger(__name__)

#: Values above this become exactly 255 (the research agent's "clamp >245").
DEFAULT_THRESHOLD = 245
#: Per-channel border average required to call the background near-white.
DEFAULT_BORDER_MIN = 248
#: Frame width (px) sampled for the border check, capped for tiny images.
BORDER_WIDTH = 4


def _border_frame(image: np.ndarray) -> np.ndarray:
    """Every pixel of the outer frame, as one (N, channels) array."""
    height, width = image.shape[:2]
    band = max(1, min(BORDER_WIDTH, min(height, width) // 4))
    rows = [
        image[:band].reshape(-1, image.shape[2]),
        image[-band:].reshape(-1, image.shape[2]),
        image[:, :band].reshape(-1, image.shape[2]),
        image[:, -band:].reshape(-1, image.shape[2]),
    ]
    return np.concatenate(rows, axis=0)


def border_is_near_white(image: np.ndarray, border_min: int = DEFAULT_BORDER_MIN) -> tuple[bool, list[int]]:
    """True when every channel of the outer frame averages >= ``border_min``.

    Returns ``(near_white, per_channel_means)`` so the caller can report the
    measured border even when it declines to clamp.
    """
    means = _border_frame(image).mean(axis=0)
    rgb_means = [int(round(value)) for value in means[::-1]]  # BGR -> RGB
    return all(value >= border_min for value in rgb_means), rgb_means


def clamp_background(
    image: np.ndarray,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    protect_subject: bool = True,
) -> tuple[np.ndarray, int]:
    """Return a copy with the background clamped to pure white.

    ``protect_subject`` restricts the clamp to the border-connected component
    of the near-white mask, preserving interior highlights. Returns
    ``(image, changed_pixel_count)``.
    """
    near_white = (image > threshold).all(axis=2).astype(np.uint8)
    if protect_subject:
        _, labels = cv2.connectedComponents(near_white, connectivity=8)
        # Labels present on the true 1px edge are the background component(s).
        ring = np.concatenate(
            [labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]
        )
        keep = np.unique(ring)
        keep = keep[keep != 0]
        region = np.isin(labels, keep) & near_white.astype(bool)
    else:
        region = near_white.astype(bool)

    if not region.any():
        return image.copy(), 0

    touched = image[region]
    changed = int(np.count_nonzero(np.any(touched < 255, axis=-1)))
    out = image.copy()
    out[region] = 255
    return out, changed


def ensure_pure_white(
    source: Path | str,
    destination: Path | str,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    border_min: int = DEFAULT_BORDER_MIN,
    protect_subject: bool = True,
) -> dict:
    """Verify the border and, when near-white, clamp the background to #FFFFFF.

    Never raises for a bad image: a decode failure returns ``ok: False`` with a
    reason the job item can show. ``applied`` distinguishes "clamped" from
    "background was not near-white, left untouched".
    """
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        return {
            "ok": False,
            "verified": False,
            "applied": False,
            "reason": f"Could not read {source}",
        }

    near_white, border_means = border_is_near_white(image, border_min)
    if not near_white:
        return {
            "ok": True,
            "verified": False,
            "applied": False,
            "reason": (
                "Background is not near-white "
                f"(border mean RGB {border_means}) - left untouched."
            ),
            "border_mean_rgb": border_means,
            "threshold": threshold,
            "clamped_pixels": 0,
        }

    clamped, changed = clamp_background(
        image, threshold=threshold, protect_subject=protect_subject
    )
    if changed:
        if not write_srgb_jpeg(clamped, destination, quality=100):
            return {"ok": False, "verified": True, "applied": False, "reason": "Could not write the clamped image."}

    return {
        "ok": True,
        "verified": True,
        "applied": changed > 0,
        "reason": (
            f"Border mean RGB {border_means}; clamped {changed} pixel(s) to 255."
            if changed
            else f"Border mean RGB {border_means}; background already pure white."
        ),
        "border_mean_rgb": border_means,
        "threshold": threshold,
        "protect_subject": protect_subject,
        "clamped_pixels": changed,
        "output_path": str(destination) if changed else None,
    }
