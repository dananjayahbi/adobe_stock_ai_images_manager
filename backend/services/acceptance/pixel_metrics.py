"""Deterministic pixel measurements used by the acceptance scorer.

All functions are pure: they take a path (or an ndarray) and return plain
numbers. No thresholds are applied here - interpretation lives in ``scorer``.
Every measurement is guarded so a corrupt image yields neutral values instead
of raising.
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

#: Longest edge used for the global (colour/tone/edge) analysis pass.
ANALYSIS_MAX_DIM = 1600

#: Side of the native-resolution centre crop used for texture analysis.
#: Adobe reviewers inspect at 100% (1:1 pixel) zoom, so noise and sharpness
#: must be measured at native resolution - downscaling averages noise away.
NATIVE_CROP_SIZE = 1024

#: sqrt(20) is the L2 norm of OpenCV's 3x3 Laplacian kernel
#: [[0,1,0],[1,-4,1],[0,1,0]]; it converts MAD back to input noise sigma.
_LAPLACIAN_KERNEL_NORM = 4.47213595499958

# Neutral fallbacks keep a single unreadable image from collapsing the score.
_NEUTRAL: dict[str, float] = {
    "clipped_highlight_ratio": 0.0,
    "crushed_shadow_ratio": 0.0,
    "mean_luma": 0.5,
    "luma_std": 0.2,
    "overall_saturation": 0.3,
    "skin_saturation": 0.0,
    "skin_pixel_ratio": 0.0,
    "green_saturation": 0.0,
    "green_pixel_ratio": 0.0,
    "laplacian_variance": 0.0,
    "tenengrad": 0.0,
    "halo_ratio": 0.0,
    "chroma_fringe_ratio": 0.0,
    "noise_sigma": 0.0,
    "flat_region_ratio": 0.0,
    "blockiness": 0.0,
    "megapixels": 0.0,
    "file_size_mb": 0.0,
}


def _load_bgr(path: str | Path, max_dim: int = ANALYSIS_MAX_DIM) -> np.ndarray | None:
    """Read an image as BGR, downscaling if it exceeds ``max_dim``."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    height, width = image.shape[:2]
    longest = max(height, width)
    if longest > max_dim:
        scale = max_dim / float(longest)
        image = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    return image


def _native_crop(image: np.ndarray, size: int = NATIVE_CROP_SIZE) -> np.ndarray:
    """Return a centre crop at native resolution (never rescaled)."""
    height, width = image.shape[:2]
    crop_h = min(height, size)
    crop_w = min(width, size)
    top = (height - crop_h) // 2
    left = (width - crop_w) // 2
    return image[top : top + crop_h, left : left + crop_w]


def _load_native_crop(path: str | Path, size: int = NATIVE_CROP_SIZE) -> np.ndarray | None:
    """Decode an image and return a 1:1 centre crop.

    Deliberately *not* routed through :func:`_load_bgr`: that helper downscales
    large images, which averages away exactly the high-frequency signal
    (sharpness, sensor noise) this crop exists to measure. Cropping instead of
    resizing keeps every pixel at its original scale.
    """
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return None
    return _native_crop(image, size)


def _channel_stats(image: np.ndarray) -> dict[str, float]:
    """Luma statistics and clipping ratios."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    total = float(gray.size)

    # A tolerance of 2 units absorbs JPEG ringing while still catching clipping.
    clipped_high = float(np.count_nonzero(gray >= 253)) / total
    crushed_low = float(np.count_nonzero(gray <= 2)) / total

    return {
        "clipped_highlight_ratio": clipped_high,
        "crushed_shadow_ratio": crushed_low,
        "mean_luma": float(gray.mean()) / 255.0,
        "luma_std": float(gray.std()) / 255.0,
    }


def _saturation_stats(image: np.ndarray) -> dict[str, float]:
    """Saturation statistics overall and per colour family (HSV space)."""
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1].astype(np.float32) / 255.0
    val = hsv[:, :, 2].astype(np.float32) / 255.0

    # Only consider pixels that actually carry colour; near-greys skew the mean.
    coloured = (sat > 0.15) & (val > 0.10)
    overall = float(sat[coloured].mean()) if np.any(coloured) else 0.0

    # Red/orange band: hue 0-20 or 160-180 (OpenCV hue is 0-179).
    skin_mask = ((hue <= 20) | (hue >= 160)) & coloured
    skin_sat = float(sat[skin_mask].mean()) if np.any(skin_mask) else 0.0
    skin_ratio = float(np.count_nonzero(skin_mask)) / float(sat.size)

    # Yellow/green band: hue 21-85.
    green_mask = (hue >= 21) & (hue <= 85) & coloured
    green_sat = float(sat[green_mask].mean()) if np.any(green_mask) else 0.0
    green_ratio = float(np.count_nonzero(green_mask)) / float(sat.size)

    return {
        "overall_saturation": overall,
        "skin_saturation": skin_sat,
        "skin_pixel_ratio": skin_ratio,
        "green_saturation": green_sat,
        "green_pixel_ratio": green_ratio,
    }


def _sharpness_stats(image: np.ndarray) -> dict[str, float]:
    """Laplacian variance plus a Tenengrad gradient energy estimate."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx * gx + gy * gy))

    return {
        "laplacian_variance": laplacian_var,
        "tenengrad": tenengrad,
    }


def _edge_artifact_stats(image: np.ndarray) -> dict[str, float]:
    """Estimate upscaler halos and chromatic fringing along strong edges.

    A halo is a bright rim: pixels that sit next to a strong gradient yet are
    brighter than their local neighbourhood.

    Chromatic aberration is specifically a *channel misalignment*, not merely a
    colourful edge. A saturated edge (a red flower against green foliage) has a
    large ``r - g`` difference but a perfectly smooth one. Fringing instead
    makes the difference channels spiky at the edge, so the detector measures
    high-frequency energy in ``r - g`` and ``b - g`` *restricted to edges*.
    That distinguishes real fringing from legitimate colour contrast.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_f = gray.astype(np.float32)

    grad_x = cv2.Sobel(gray_f, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray_f, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)

    # Edges = top decile of gradient energy.
    threshold = float(np.percentile(magnitude, 90))
    if threshold <= 1e-6:
        return {"halo_ratio": 0.0, "chroma_fringe_ratio": 0.0}

    edge_mask = magnitude >= threshold
    edge_count = float(np.count_nonzero(edge_mask))
    if edge_count <= 0:
        return {"halo_ratio": 0.0, "chroma_fringe_ratio": 0.0}

    local_median = cv2.medianBlur(gray, 5).astype(np.float32)
    # A halo is a locally-bright rim: >12 luma units above the neighbourhood.
    halo_mask = edge_mask & (gray_f - local_median > 12.0)

    # Fringing: high-frequency spikes in the colour-difference channels.
    blue, green, red = cv2.split(image.astype(np.float32))
    red_diff = red - green
    blue_diff = blue - green

    # A Laplacian of the difference channel isolates the spike; its magnitude at
    # an edge pixel is large only when the channels are spatially misaligned.
    spike = np.maximum(
        np.abs(cv2.Laplacian(red_diff, cv2.CV_32F, ksize=3)),
        np.abs(cv2.Laplacian(blue_diff, cv2.CV_32F, ksize=3)),
    )
    # 25 units of curvature in a difference channel is well beyond JPEG ringing
    # in a smooth colour gradient.
    fringe_mask = edge_mask & (spike > 25.0)

    return {
        "halo_ratio": float(np.count_nonzero(halo_mask)) / edge_count,
        "chroma_fringe_ratio": float(np.count_nonzero(fringe_mask)) / edge_count,
    }


def _texture_stats(image: np.ndarray) -> dict[str, float]:
    """Noise sigma, flat-region share, and JPEG blockiness.

    Generative models and neural upscalers produce unnaturally flat surfaces;
    real camera sensors carry a low-amplitude noise floor. The median absolute
    deviation of a Laplacian is a robust noise estimator that ignores edges.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)

    laplacian = cv2.Laplacian(gray, cv2.CV_32F, ksize=3)
    # 1.4826 * MAD = sigma for normally distributed data; dividing by the
    # kernel norm converts the post-filter spread back to input noise sigma.
    mad = float(np.median(np.abs(laplacian - np.median(laplacian))))
    noise_sigma = 1.4826 * mad / _LAPLACIAN_KERNEL_NORM

    # Flat regions: local standard deviation below 2 luma units.
    local_mean = cv2.blur(gray, (7, 7))
    local_sq_mean = cv2.blur(gray * gray, (7, 7))
    local_var = np.clip(local_sq_mean - local_mean * local_mean, 0.0, None)
    flat_ratio = float(np.count_nonzero(local_var < 4.0)) / float(gray.size)

    # Blockiness: mean absolute difference across 8-pixel block boundaries
    # versus interior differences. >1 means visible JPEG grid artefacts.
    horizontal = np.abs(np.diff(gray, axis=1))
    vertical = np.abs(np.diff(gray, axis=0))
    block_h = horizontal[:, 7::8].mean() if horizontal.shape[1] > 8 else 0.0
    block_v = vertical[7::8, :].mean() if vertical.shape[0] > 8 else 0.0
    interior_h = horizontal.mean() if horizontal.size else 0.0
    interior_v = vertical.mean() if vertical.size else 0.0
    interior = (interior_h + interior_v) / 2.0 or 1e-6
    blockiness = float(((block_h + block_v) / 2.0) / interior)

    return {
        "noise_sigma": float(noise_sigma),
        "flat_region_ratio": flat_ratio,
        "blockiness": blockiness,
    }


def _container_stats(path: str | Path) -> dict[str, float]:
    """Format, colour-mode, and size facts read from the file container."""
    file_path = Path(path)
    stats = {
        "megapixels": 0.0,
        "file_size_mb": 0.0,
        "is_jpeg": 0.0,
        "is_srgb": 0.0,
        "has_icc_profile": 0.0,
        "has_alpha": 0.0,
    }

    try:
        stats["file_size_mb"] = file_path.stat().st_size / (1024 * 1024)
    except OSError:
        pass

    try:
        with Image.open(file_path) as img:
            stats["is_jpeg"] = 1.0 if (img.format or "").upper() in ("JPEG", "MPO") else 0.0
            width, height = img.size
            stats["megapixels"] = (width * height) / 1_000_000
            stats["has_alpha"] = 1.0 if "A" in img.mode else 0.0

            icc = img.info.get("icc_profile")
            stats["has_icc_profile"] = 1.0 if icc else 0.0
            if img.mode in ("RGB", "L"):
                # Adobe requires "JPEG with sRGB color profile". A wrong profile
                # is actively dangerous; a missing one is treated as sRGB, which
                # is the near-universal convention for untagged JPEG.
                if not icc:
                    stats["is_srgb"] = 1.0
                else:
                    stats["is_srgb"] = 1.0 if _icc_is_srgb(icc) else 0.0
            else:
                stats["is_srgb"] = 0.0
    except Exception:  # noqa: BLE001 - corrupt file must not crash the scorer
        logger.warning("Could not read container stats for %s", file_path)

    return stats


def _icc_is_srgb(icc_bytes: bytes) -> bool:
    """Best-effort sRGB detection: look for the profile description string."""
    lowered = icc_bytes.lower()
    return b"srgb" in lowered or b"iec61966" in lowered


def measure(path: str | Path) -> tuple[dict[str, float], np.ndarray | None]:
    """Run every measurement on ``path``.

    Returns a tuple of (metrics, image). ``image`` is the downscaled BGR array,
    returned so callers (the refiner) can reuse it without a second decode.

    Texture and sharpness are measured on a native-resolution centre crop
    because downscaling averages away exactly the high-frequency signal they
    are meant to quantify.
    """
    metrics: dict[str, float] = dict(_NEUTRAL)
    image = _load_bgr(path)

    metrics.update(_container_stats(path))
    if image is None:
        logger.warning("Could not decode image for measurement: %s", path)
        return metrics, None

    metrics.update(_channel_stats(image))
    metrics.update(_saturation_stats(image))
    metrics.update(_edge_artifact_stats(image))

    # Sample a native-resolution centre crop for the high-frequency measures.
    # Sharpness and noise live in exactly the detail that downscaling averages
    # away, so they must be read at 1:1 - which is also the zoom level Adobe's
    # reviewers inspect at.
    native = _load_native_crop(path)
    sample = native if native is not None else image
    metrics.update(_sharpness_stats(sample))
    metrics.update(_texture_stats(sample))

    return metrics, image
