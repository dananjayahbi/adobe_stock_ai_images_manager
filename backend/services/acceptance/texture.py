"""Scene-aware noise and texture measurement.

Why a single global noise number is wrong: Adobe rejected a file shot at
**ISO 160** for noise, because it was a clear blue sky - a flat field where any
noise is visible. The same noise sigma inside foliage is invisible. Adobe
therefore applies a *visibility* judgement, not a threshold, and it publishes no
numeric limit at all.

So noise is measured over the **flattest share of the frame**, where a reviewer
can actually see it. Two designs were tried and rejected:

* **Hard-threshold region split** (classify each pixel as flat/textured, then
  measure inside each group). This fails badly: heavy noise raises the local
  standard deviation above the "flat" cut, so the noisiest images classify *no*
  pixels as flat and report a noise level of **zero** - the noisier the image,
  the better it scored.
* **Whole-frame sigma.** Cannot distinguish noise from real texture, so foliage
  and gravel read as noise.

A percentile ("the flattest 30% of the frame") can never run out of pixels, so
it tracks injected noise almost exactly linearly while still discounting real
texture.
"""

from __future__ import annotations

import cv2
import numpy as np

#: sqrt(20) is the L2 norm of OpenCV's 3x3 Laplacian kernel, converting the
#: post-filter spread back to input noise sigma.
LAPLACIAN_KERNEL_NORM = 4.47213595499958

#: Share of the frame (by local flatness) over which noise is measured.
FLATTEST_FRACTION = 0.30

#: Local-statistics window for the flatness ranking.
FLAT_WINDOW = 7


def _mad_sigma(values: np.ndarray) -> float:
    """Robust sigma from the median absolute deviation of ``values``."""
    if values.size < 64:
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return 1.4826 * mad / LAPLACIAN_KERNEL_NORM


def _local_std(gray: np.ndarray) -> np.ndarray:
    """Per-pixel local standard deviation over a small window."""
    mean = cv2.blur(gray, (FLAT_WINDOW, FLAT_WINDOW))
    mean_sq = cv2.blur(gray * gray, (FLAT_WINDOW, FLAT_WINDOW))
    variance = np.clip(mean_sq - mean * mean, 0.0, None)
    return np.sqrt(variance)


def measure_noise_visible(gray: np.ndarray) -> float:
    """Noise sigma over the flattest share of the frame.

    This is the value that predicts a "noise" refusal, because it measures noise
    where a reviewer can see it. It cannot collapse to zero: a percentile always
    selects pixels.

    Args:
        gray: Single-channel float image (native 1:1 resolution).

    Returns:
        Noise sigma in 8-bit luma units.
    """
    if gray.size == 0:
        return 0.0

    local_std = _local_std(gray)
    cutoff = float(np.percentile(local_std, FLATTEST_FRACTION * 100.0))
    mask = local_std <= cutoff
    if int(np.count_nonzero(mask)) < 256:
        # Degenerate frame (all one value): fall back to the global estimate.
        return _mad_sigma(np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3)))

    laplacian = np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))
    return _mad_sigma(laplacian[mask])


def measure_texture(image: np.ndarray) -> dict[str, float]:
    """Measure noise where it is visible, plus the flat-region share.

    Args:
        image: BGR image array. Should be a **native 1:1** sample: downscaling
            averages away the high-frequency signal being measured.

    Returns:
        ``noise_sigma`` (whole-frame, diagnostic), ``noise_sigma_flat`` (the
        scored value), ``flat_region_ratio``, and ``blockiness``.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)

    local_std = _local_std(gray)
    flat_ratio = float(np.count_nonzero(local_std < 2.0)) / float(gray.size)

    return {
        "noise_sigma": _mad_sigma(np.abs(cv2.Laplacian(gray, cv2.CV_32F, ksize=3))),
        "noise_sigma_flat": measure_noise_visible(gray),
        "flat_region_ratio": flat_ratio,
        "blockiness": measure_blockiness(gray),
    }


def measure_blockiness(gray: np.ndarray) -> float:
    """JPEG grid artefact ratio: block-boundary gradients vs interior ones.

    A value above ~1.0 indicates a visible 8x8 compression grid.
    """
    horizontal = np.abs(np.diff(gray, axis=1))
    vertical = np.abs(np.diff(gray, axis=0))
    block_h = horizontal[:, 7::8].mean() if horizontal.shape[1] > 8 else 0.0
    block_v = vertical[7::8, :].mean() if vertical.shape[0] > 8 else 0.0
    interior_h = horizontal.mean() if horizontal.size else 0.0
    interior_v = vertical.mean() if vertical.size else 0.0
    interior = (interior_h + interior_v) / 2.0 or 1e-6
    return float(((block_h + block_v) / 2.0) / interior)


def noise_visibility_weight(image: np.ndarray) -> np.ndarray:
    """Per-pixel weight in ``[0, 1]`` for how visible noise is at that pixel.

    Adobe's criterion is visibility, not amplitude: noise is objectionable in a
    smooth sky and invisible in foliage. This weight is 1.0 where the local
    neighbourhood is flat and falls off where real texture masks the noise.

    Args:
        image: BGR image array.

    Returns:
        A float32 array of the same height/width, 1.0 = maximally visible.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    local_std = _local_std(gray)
    # Smooth transition around the flat threshold so the weight does not create
    # hard-edged denoise boundaries (which would themselves look like artefacts).
    weight = 1.0 - np.clip(local_std / 4.0, 0.0, 1.0)
    return cv2.GaussianBlur(weight.astype(np.float32), (0, 0), 3.0)
