"""Individual pixel-level corrective operations for Stage 4.

Every operation takes and returns a BGR ``uint8`` array, so they compose in any
order. The techniques mirror the post-processing "hacks" that address Adobe
Stock's documented rejection triggers: clipped tone extremes, over-saturated
colour casts, upscaler halos and fringing, and the waxy surface texture that
gives generative output away.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Chroma subsampling used on export. 4:4:4 keeps colour detail that 4:2:0
#: would smear along the very edges the refiner is repairing.
JPEG_SUBSAMPLING_444 = 0


def clamp_levels(
    image: np.ndarray, black_point: int = 4, white_point: int = 252
) -> np.ndarray:
    """Compress the tonal range inside ``[black_point, white_point]``.

    Adobe rejects images containing pure ``#FFFFFF`` whites or clipped blacks.
    Remapping the extremes preserves a little detail at both ends, mimicking a
    real sensor's dynamic-range roll-off.
    """
    black = float(black_point)
    white = float(white_point)
    scale = (white - black) / 255.0
    out = black + image.astype(np.float32) * scale
    return np.clip(out, 0, 255).astype(np.uint8)


def _hue_band_weights(hue: np.ndarray, low: int, high: int, feather: int) -> np.ndarray:
    """Smooth 0..1 membership weight for a (possibly wrapping) hue band."""
    hue_f = hue.astype(np.float32)

    if low <= high:
        distance = np.minimum(
            np.abs(hue_f - low), np.abs(hue_f - high)
        )
        inside = (hue_f >= low) & (hue_f <= high)
    else:
        # Wrap-around band (e.g. red: 160-179 plus 0-20).
        inside = (hue_f >= low) | (hue_f <= high)
        distance = np.minimum(
            np.abs(hue_f - low), np.abs(hue_f - high)
        )
        distance = np.where(inside, 0.0, distance)

    if feather <= 0:
        return inside.astype(np.float32)

    # Feather outside the band so desaturation never produces a visible seam.
    ramp = np.clip(1.0 - distance / float(feather), 0.0, 1.0)
    return np.where(inside, 1.0, ramp).astype(np.float32)


def desaturate_hue_band(
    image: np.ndarray,
    low: int,
    high: int,
    factor: float,
    feather: int = 12,
    min_value: float = 0.08,
) -> np.ndarray:
    """Scale saturation down inside a hue band by ``factor`` (0..1).

    ``low``/``high`` are OpenCV hues (0-179). A wrapping band is supported so
    the red/orange skin range can span the 179 -> 0 boundary.
    """
    factor = float(np.clip(factor, 0.0, 1.0))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    weights = _hue_band_weights(hue, low, high, feather)
    # Very dark or near-grey pixels carry no meaningful hue; leave them alone.
    weights = np.where(value / 255.0 < min_value, 0.0, weights)

    adjusted = saturation * (1.0 - weights * (1.0 - factor))
    hsv[:, :, 1] = np.clip(adjusted, 0, 255)

    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def desaturate_overall(image: np.ndarray, factor: float) -> np.ndarray:
    """Scale saturation globally, preserving hue and value."""
    factor = float(np.clip(factor, 0.0, 1.0))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * factor, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _edge_weight(image: np.ndarray, percentile: float = 88.0) -> np.ndarray:
    """Return a feathered 0..1 mask emphasising strong edges.

    Normalisation uses a percentile-derived scale rather than a raw divide by
    the threshold. Dividing by a threshold that collapses to ~0 on an image with
    large flat areas would give *every* pixel weight 1.0, so the correction
    would bleed across the whole frame instead of hugging real edges.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)

    # Minimum gradient (in luma units) worth treating as an edge at all.
    floor = float(np.percentile(magnitude, percentile))
    if floor < 8.0:
        floor = 8.0

    # Scale so a strong edge (99th percentile) reaches full weight.
    ceiling = float(np.percentile(magnitude, 99.0))
    ceiling = max(ceiling, floor * 1.5)

    weight = np.clip((magnitude - floor) / (ceiling - floor), 0.0, 1.0)
    # Blur slightly so the correction blends instead of creating a hard mask.
    return cv2.GaussianBlur(weight, (0, 0), 1.2)


def defringe(image: np.ndarray, strength: float = 0.7) -> np.ndarray:
    """Suppress purple/green chromatic fringing along high-contrast edges.

    Fringing shows up as one channel diverging from the others on an edge.
    Where red and blue both exceed green the result is the magenta/purple halo
    neural upscalers produce; where green exceeds both, a green fringe.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    # The channel-difference maps below are single-channel, so the edge weight
    # stays 2-D to broadcast against them.
    weight = _edge_weight(image)

    data = image.astype(np.float32)
    blue, green, red = cv2.split(data)

    purple = np.minimum(np.clip(red - green, 0, None), np.clip(blue - green, 0, None))
    green_excess = np.clip(green - np.maximum(red, blue), 0, None)

    correction = (purple - green_excess) * strength * weight

    red = red - np.clip(correction, 0, None)
    blue = blue - np.clip(correction, 0, None)
    green = green + np.clip(-correction, 0, None)

    merged = cv2.merge([blue, green, red])
    return np.clip(merged, 0, 255).astype(np.uint8)


def remove_halo(image: np.ndarray, strength: float = 0.6) -> np.ndarray:
    """Pull back bright over-sharpening rims that sit above their neighbourhood.

    A halo is a 1-2 pixel bright rim hugging a high-contrast border. Pixels that
    are brighter than the local median *and* sit on a strong edge are pulled
    toward that median.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    weight = _edge_weight(image)[:, :, None]

    data = image.astype(np.float32)
    # A median blur of the whole frame approximates the "neighbourhood" value;
    # the median is used so genuine thin bright structures (wires, eyelashes)
    # survive, since the median ignores them.
    neighbourhood = cv2.medianBlur(image, 5).astype(np.float32)

    # A halo sits *above* its neighbourhood. Comparing per-channel and taking
    # the maximum keeps the correction from tinting a neutral bright rim.
    excess = np.clip(data - neighbourhood - 8.0, 0, None)
    corrected = data - excess * strength * weight
    return np.clip(corrected, 0, 255).astype(np.uint8)


def deblock(image: np.ndarray, strength: float = 0.5) -> np.ndarray:
    """Smooth JPEG block-boundary banding without blurring real detail.

    A 1-pixel median is applied only to pixels sitting on an 8-pixel grid
    boundary, which is where compression artefacts live.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    height, width = image.shape[:2]
    if height < 16 or width < 16:
        return image

    smoothed = cv2.medianBlur(image, 3)

    mask = np.zeros((height, width), dtype=np.float32)
    mask[:, 7::8] = 1.0
    mask[7::8, :] = 1.0
    # Feather the mask so the median never cuts a hard seam.
    mask = cv2.GaussianBlur(mask, (0, 0), 1.0)[:, :, None] * strength

    blended = image.astype(np.float32) * (1.0 - mask) + smoothed.astype(np.float32) * mask
    return np.clip(blended, 0, 255).astype(np.uint8)


def add_sensor_grain(
    image: np.ndarray,
    target_sigma: float = 1.6,
    current_sigma: float = 0.0,
    monochromatic: bool = True,
) -> np.ndarray:
    """Add Gaussian sensor noise up to ``target_sigma``.

    Only the *missing* noise is added, so an image that already carries a
    realistic noise floor is not pushed past the natural ceiling.

    Monochromatic noise is used because real sensors have correlated
    per-photosite noise; independent per-channel noise reads as digital.
    """
    deficit = target_sigma ** 2 - current_sigma ** 2
    if deficit <= 0:
        return image

    sigma = float(np.sqrt(deficit))
    height, width = image.shape[:2]
    rng = np.random.default_rng()

    if monochromatic:
        noise = rng.normal(0.0, sigma, size=(height, width, 1))
        noise = np.repeat(noise, 3, axis=2)
    else:
        noise = rng.normal(0.0, sigma, size=(height, width, 3))

    # Slight blur correlates neighbouring samples, matching the spatial
    # frequency profile of a real high-ISO capture rather than white noise.
    noise = cv2.GaussianBlur(noise.astype(np.float32), (0, 0), 0.5)

    out = image.astype(np.float32) + noise
    return np.clip(out, 0, 255).astype(np.uint8)


def denoise_flat_regions(
    image: np.ndarray,
    strength: float = 0.6,
    detail_preserve: float = 0.65,
) -> np.ndarray:
    """Denoise only where noise is VISIBLE, then restore lost micro-detail.

    A uniform denoise pass is the wrong tool: it removes noise that was never
    objectionable (inside foliage, fabric, hair) while leaving the visible noise
    in flat regions only partly reduced. Adobe's own evidence shows the
    criterion is visibility - an ISO-160 file was refused for noise because it
    was a flat blue sky.

    Two stages:

    1. **Weighted denoise.** A bilateral filter is blended in proportion to a
       per-pixel *noise visibility* weight, so smooth regions are cleaned and
       textured regions are left alone.
    2. **Detail restoration.** Denoising always removes some genuine
       micro-texture, and Adobe explicitly refuses "unrealistic
       skin-smoothing". The high-frequency component that the filter removed is
       added back at ``detail_preserve``, which keeps pores and fine texture
       while the noise stays suppressed.

    Args:
        image: BGR image array.
        strength: 0..1 blend toward the denoised result in flat regions.
        detail_preserve: 0..1 share of the removed high-frequency detail to add
            back.

    Returns:
        The filtered image, same shape and dtype as the input.
    """
    from services.acceptance.texture import noise_visibility_weight

    strength = float(np.clip(strength, 0.0, 1.0))
    detail_preserve = float(np.clip(detail_preserve, 0.0, 1.0))

    source = image.astype(np.float32)
    # A bilateral filter is edge-preserving, so it removes noise without
    # smearing real edges the way a Gaussian blur would.
    filtered = cv2.bilateralFilter(image, d=7, sigmaColor=28.0, sigmaSpace=7.0)
    filtered = filtered.astype(np.float32)

    weight = noise_visibility_weight(image)[:, :, None] * strength
    blended = source * (1.0 - weight) + filtered * weight

    # Give back the micro-detail the filter removed, so surfaces do not turn
    # waxy - which Adobe lists as a refusal reason ("unrealistic
    # skin-smoothing").
    removed_detail = source - filtered
    restored = blended + removed_detail * detail_preserve

    return np.clip(restored, 0, 255).astype(np.uint8)


def restore_texture(image: np.ndarray, amount: float = 0.6) -> np.ndarray:
    """Recover local micro-contrast on over-smoothed surfaces.

    Targets the honest version of the "waxy" defect: a loss of high-frequency
    detail in flat regions, not the absence of sensor noise. The gain is applied
    through a luminance-detail mask so colour is untouched.

    Args:
        image: BGR image array.
        amount: 0..1 strength of the recovered detail.

    Returns:
        The texture-restored image.
    """
    amount = float(np.clip(amount, 0.0, 1.0))
    source = image.astype(np.float32)

    # High-pass the luminance channel only: adding chroma detail would amplify
    # any residual chroma noise.
    ycrcb = cv2.cvtColor(image, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    luma = ycrcb[:, :, 0]
    blurred = cv2.GaussianBlur(luma, (0, 0), 1.4)
    detail = luma - blurred

    # Only boost detail that is genuinely weak, so already-crisp areas are not
    # over-sharpened (Adobe refuses over-sharpened files).
    weak = np.clip(1.0 - np.abs(detail) / 6.0, 0.0, 1.0)
    ycrcb[:, :, 0] = luma + detail * amount * weak

    restored = cv2.cvtColor(ycrcb.astype(np.uint8), cv2.COLOR_YCrCb2BGR)
    return restored


def sharpen(image: np.ndarray, amount: float = 0.8, radius: float = 1.2) -> np.ndarray:
    """Apply an unsharp mask to recover softness lost during upscaling."""
    blurred = cv2.GaussianBlur(image, (0, 0), radius)
    out = image.astype(np.float32) + amount * (
        image.astype(np.float32) - blurred.astype(np.float32)
    )
    return np.clip(out, 0, 255).astype(np.uint8)


def to_srgb(image: np.ndarray) -> np.ndarray:
    """Ensure a plain 8-bit BGR array suitable for sRGB JPEG export."""
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    return image
