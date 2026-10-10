"""Auto-trimap generation for two-stage (segmentation → matting) pipelines.

A salient-object model only knows "object / not object". A neural matte needs
three states so it can concentrate all of its capacity on the pixels that are
genuinely ambiguous:

* **definite foreground** (255) — solidly inside the mask (eroded)
* **unknown** (128)           — the transition band (between erode and dilate)
* **definite background** (0) — solidly outside the mask (dilated)

The band width is the erode/dilate radius; the research blueprint recommends
3-8px for stock imagery, which is wide enough to swallow sub-pixel antialiasing
and hair tips but tight enough that the matte is not being asked to solve the
whole object.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Trimap value for "definitely background".
BACKGROUND = 0
#: Trimap value for "unknown — solve me".
UNKNOWN = 128
#: Trimap value for "definitely foreground".
FOREGROUND = 255

#: Recommended band half-width in pixels for stock cut-outs. 4px (8px total)
#: sits inside the 3-8px band the research recommends while leaving the matte
#: only a narrow strip to solve — a wider band ends up as a milky edge.
DEFAULT_RADIUS = 4


def _ellipse(radius: int) -> np.ndarray:
    """A (2r+1) circular structuring element."""
    r = max(1, int(radius))
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def build_trimap(alpha: np.ndarray, radius: int = DEFAULT_RADIUS) -> np.ndarray:
    """Split a coarse alpha mask into definite-FG / unknown / definite-BG.

    ``alpha`` is any HxW array (float 0-255 or 0-1, or uint8); only the
    ``> 127`` decision matters, because the trimap is a *geometry* hint — the
    sub-pixel values are the matte's job, not this function's.
    """
    mask = (np.asarray(alpha) > 127).astype(np.uint8)
    if not mask.any():
        return np.zeros(mask.shape, dtype=np.uint8)
    if mask.all():
        return np.full(mask.shape, FOREGROUND, dtype=np.uint8)

    kernel = _ellipse(radius)
    definite_fg = cv2.erode(mask, kernel)
    definite_bg = cv2.dilate(mask, kernel)

    trimap = np.full(mask.shape, UNKNOWN, dtype=np.uint8)
    trimap[definite_bg == BACKGROUND] = BACKGROUND
    trimap[definite_fg > 0] = FOREGROUND
    return trimap


def unknown_fraction(trimap: np.ndarray) -> float:
    """Share of pixels left for the matte — 0 means nothing to refine."""
    total = trimap.size
    if total == 0:
        return 0.0
    return float(np.count_nonzero(trimap == UNKNOWN)) / float(total)
