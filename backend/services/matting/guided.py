"""Edge-aware guided filter — the offline sub-pixel refiner.

The guided filter smooths a guidance map (here: the trimap) while keeping its
edges aligned to a reference image (here: the photo). Applied to a trimap it
turns a three-valued geometry hint into a soft alpha that *follows image edges*
instead of a disk blur — which is exactly the difference between a jagged
stair-step and a clean sub-pixel boundary.

Implemented with ``cv2.boxFilter`` only, so it needs no GPU, no model download
and no extra dependency: it is the refiner that is always available.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Box-filter window (odd side length) for the local statistics.
DEFAULT_RADIUS = 8
#: Regularisation. Larger = smoother, less edge-faithful. Works on 0-1 data.
DEFAULT_EPS = 0.01


def _box(img: np.ndarray, radius: int) -> np.ndarray:
    k = (2 * int(radius) + 1, 2 * int(radius) + 1)
    return cv2.boxFilter(img, ddepth=cv2.CV_64F, ksize=k, normalize=True)


def guided_filter(
    guide: np.ndarray,
    source: np.ndarray,
    radius: int = DEFAULT_RADIUS,
    eps: float = DEFAULT_EPS,
) -> np.ndarray:
    """Filter ``source`` guided by ``guide`` (both 2-D, any scale, 0-1 out).

    Outputs are clipped to the source's own range so callers can treat the
    result as a probability/alpha without extra clamping.
    """
    g = np.asarray(guide, dtype=np.float64)
    s = np.asarray(source, dtype=np.float64)
    if g.ndim != 2 or s.ndim != 2 or g.shape != s.shape:
        raise ValueError("guided_filter expects two matching 2-D arrays")
    r = max(1, int(radius))
    eps = max(float(eps), 1e-9)

    mean_g = _box(g, r)
    mean_s = _box(s, r)
    corr_g = _box(g * g, r)
    corr_gs = _box(g * s, r)

    var_g = corr_g - mean_g * mean_g
    cov_gs = corr_gs - mean_g * mean_s

    a = cov_gs / (var_g + eps)
    b = mean_s - a * mean_g

    out = _box(a, r) * g + _box(b, r)
    lo, hi = float(np.min(s)), float(np.max(s))
    return np.clip(out, lo, hi)


def luma(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luma of an HxWx3 uint8/float image, normalised to 0-1."""
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.ndim == 2:
        return arr / 255.0
    gray = (
        0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    )
    return gray / 255.0
