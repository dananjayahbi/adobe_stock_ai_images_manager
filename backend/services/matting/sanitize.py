"""Stage 5: alpha sanitising — the zero-defect stock guard.

Three deterministic filters that run after any matte, in the order their
failure modes compound:

1. **choke**      — a sub-pixel inward pull that swallows the last
   single-pixel band of transition fuzz a soft matte always leaves behind.
2. **hard cutoff** — Adobe's own auto-checker flags faint "dust" pixels in the
   transparent region; anything below 8/255 is not a subject, it is noise, so
   it becomes exactly 0 rather than a 3% whisper.
3. **island filter** — connected components of the alpha that are too small to
   be subject matter (sensor dust, a stray leaf fragment) are removed outright.
   Detached *parts* of a spindly subject are kept by raising
   ``min_island_px`` — the filter only ever removes whole disconnected
   components, never pixels inside a connected one, so antennae and legs that
   touch the body are never cut.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

#: Research default: 0.5-1.0px of inward pull.
DEFAULT_CHOKE_PX = 0.5
#: Anything below this alpha (0-255) is background, not subject.
DEFAULT_HARD_CUTOFF = 8
#: Smallest disconnected component worth keeping (30-50px recommended).
DEFAULT_MIN_ISLAND_PX = 40


def _kernel() -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


def choke(alpha_u8: np.ndarray, pixels: float) -> np.ndarray:
    """Erode the alpha by a *fractional* number of pixels.

    Whole pixels use a real morphological erosion; the fractional remainder
    blends the eroded result with the original, which is a genuine
    0.5px pull rather than a rounded-off 1px bite.
    """
    amount = float(np.clip(pixels, 0.0, 8.0))
    if amount <= 0.0:
        return alpha_u8
    whole = int(math.floor(amount))
    fraction = amount - whole

    out = alpha_u8
    if whole:
        out = cv2.erode(out, _kernel(), iterations=whole)
    if fraction > 0.0:
        eroded = cv2.erode(out, _kernel())
        blended = (1.0 - fraction) * out.astype(np.float32) + fraction * eroded
        out = np.round(blended).astype(np.uint8)
    return out


def remove_islands(alpha_u8: np.ndarray, min_area: int) -> tuple[np.ndarray, int, int]:
    """Drop disconnected alpha components smaller than ``min_area`` pixels.

    Returns ``(alpha, components_removed, pixels_removed)``.
    """
    if min_area <= 0:
        return alpha_u8, 0, 0
    binary = (alpha_u8 > 0).astype(np.uint8)
    if not binary.any():
        return alpha_u8, 0, 0

    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    removed = 0
    removed_px = 0
    for label in range(1, count):
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < min_area:
            alpha_u8[labels == label] = 0
            removed += 1
            removed_px += area
    return alpha_u8, removed, removed_px


def sanitize_alpha(
    rgba: np.ndarray,
    *,
    choke_px: float = DEFAULT_CHOKE_PX,
    hard_cutoff: int = DEFAULT_HARD_CUTOFF,
    min_island_px: int = DEFAULT_MIN_ISLAND_PX,
) -> tuple[np.ndarray, dict]:
    """Apply choke → cutoff → island filter. Returns (rgba, stats)."""
    arr = np.array(rgba, dtype=np.uint8, copy=True)
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("sanitize_alpha expects an HxWx4 RGBA array")

    alpha = arr[..., 3]
    before = int(np.count_nonzero(alpha))

    alpha = choke(alpha, choke_px)
    if hard_cutoff > 0:
        alpha[alpha < int(hard_cutoff)] = 0
    alpha, islands, island_px = remove_islands(alpha, int(min_island_px))

    arr[..., 3] = alpha
    stats = {
        "choke_px": float(choke_px),
        "hard_cutoff": int(hard_cutoff),
        "min_island_px": int(min_island_px),
        "islands_removed": islands,
        "island_pixels": island_px,
        "alpha_px_before": before,
        "alpha_px_after": int(np.count_nonzero(alpha)),
    }
    return arr, stats


__all__ = [
    "DEFAULT_CHOKE_PX",
    "DEFAULT_HARD_CUTOFF",
    "DEFAULT_MIN_ISLAND_PX",
    "choke",
    "remove_islands",
    "sanitize_alpha",
]
