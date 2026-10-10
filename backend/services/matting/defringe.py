"""Stage 4: colour decontamination (defringing).

Even a geometrically perfect mask keeps the physics of the original capture:
at the boundary the sensor already mixed the object's light with the backdrop's
light, so every edge pixel is

    P = a*F + (1-a)*B

Placed on Adobe's white *or* black inspection canvas those pixels still carry
``B``, which reads as a coloured outline — the single most common reason a
otherwise-clean cut-out gets flagged.

The fix is the un-blend: solve for the pure foreground colour,

    F = (P - (1-a)B) / a

with ``B`` taken per-pixel from the *nearest* near-transparent pixel, so a
gradient or patterned backdrop is followed instead of averaged away.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Alpha (0-255) at or below which a pixel counts as pure backdrop.
EXT_ALPHA = 16
#: Alpha (0-255) below which un-blending is pointless (sanitize will cut it).
MIN_ALPHA = 14
#: How far (px) a fringe pixel may be from real backdrop and still get fixed.
MAX_REACH = 160.0


def nearest_colour(
    rgb: np.ndarray,
    source: np.ndarray,
    query: np.ndarray,
    *,
    max_reach: float = MAX_REACH,
) -> tuple[np.ndarray, np.ndarray]:
    """Nearest ``source``-pixel colour for every pixel flagged in ``query``.

    Returns ``(colours N x 3 float32, reached N bool)`` — ``reached`` is False
    where the query pixel had no source pixel within ``max_reach``.
    """
    rgb = np.asarray(rgb)
    src = np.asarray(source).astype(bool)
    mask = np.asarray(query).astype(bool)
    empty = (np.zeros((0, 3), dtype=np.float32), np.zeros(0, dtype=bool))

    idx = np.flatnonzero(mask)
    if idx.size == 0 or not src.any():
        return empty

    # The distance/label maps run over the whole frame but are only two HxW
    # integer arrays; only the query subset is expanded to coordinates, so
    # memory stays proportional to the fringe, not to the image.
    inv = (~src).astype(np.uint8)
    dist, labels = cv2.distanceTransformWithLabels(
        inv, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
    )

    coords = np.argwhere(src)  # raster order == DIST_LABEL_PIXEL numbering
    flat = labels.reshape(-1)[idx] - 1
    valid = (flat >= 0) & (flat < coords.shape[0])
    if not valid.any():
        return empty

    chosen = coords[flat[valid]]
    colours = rgb[chosen[:, 0], chosen[:, 1]].astype(np.float32)
    reached = dist.reshape(-1)[idx][valid] <= float(max_reach)
    return colours, reached


def estimate_background(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    ext_alpha: int = EXT_ALPHA,
) -> tuple[np.ndarray | None, dict]:
    """Mean colour of the transparent surround — a whole-image ``B`` guess.

    Used only as a fallback/report value; :func:`decontaminate` prefers the
    per-pixel nearest-backdrop estimate.
    """
    arr = np.asarray(rgb)
    a = np.asarray(alpha)
    near = a <= ext_alpha
    notes: dict = {"exterior_px": int(near.sum())}
    if near.sum() < 32:
        return None, {**notes, "reason": "not enough transparent surround"}
    px = arr[near].reshape(-1, arr.shape[-1]).astype(np.float64)
    spread = float(np.max(px.std(axis=0)))
    notes["spread"] = round(spread, 2)
    if spread > 48.0:
        return None, {**notes, "reason": "surround is not a single colour"}
    return np.round(px.mean(axis=0)).astype(np.float32), notes


def decontaminate(
    rgba: np.ndarray,
    *,
    strength: float = 1.0,
    ext_alpha: int = EXT_ALPHA,
    min_alpha: int = MIN_ALPHA,
) -> tuple[np.ndarray, dict]:
    """Un-blend backdrop colour out of the soft edge. Returns (rgba, notes).

    ``strength=1`` fully un-blends; ``0`` is a no-op. Only pixels with a real
    soft edge are touched — solid foreground and fully transparent pixels keep
    their colour untouched.
    """
    arr = np.array(rgba, dtype=np.uint8, copy=True)
    notes: dict = {"applied": False}
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("decontaminate expects an HxWx4 RGBA array")

    alpha = arr[..., 3].astype(np.float32)
    fringe = (alpha > 0) & (alpha < 255)
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength == 0.0 or not fringe.any():
        notes["reason"] = "no soft edge to un-blend" if not fringe.any() else "disabled"
        return arr, notes

    ext = alpha <= ext_alpha
    if not ext.any():
        notes["reason"] = "no transparent surround to estimate the backdrop from"
        return arr, notes

    target = fringe & (alpha >= min_alpha)
    if not target.any():
        notes["reason"] = "soft edge below the decontamination floor"
        return arr, notes

    colours, reached = nearest_colour(arr[..., :3], ext, target)
    if reached.sum() < 16:
        notes["reason"] = "backdrop estimate unreachable"
        return arr, notes

    idx = np.flatnonzero(target)[reached]
    obs = arr.reshape(-1, 4)[idx, :3].astype(np.float32)
    a = (alpha.reshape(-1)[idx] / 255.0).astype(np.float32)
    bg = colours[reached]

    denom = np.maximum(a, MIN_ALPHA / 255.0)[..., None]
    pure = np.clip((obs - (1.0 - a)[..., None] * bg) / denom, 0.0, 255.0)
    corrected = obs + strength * (pure - obs)

    flat = arr.reshape(-1, 4)
    flat[idx, :3] = np.round(corrected).astype(np.uint8)
    arr = flat.reshape(arr.shape)

    notes.update(
        {
            "applied": True,
            "strength": strength,
            "pixels": int(idx.size),
            "max_shift": round(float(np.abs(corrected - obs).max()), 1),
        }
    )
    return arr, notes


__all__ = [
    "EXT_ALPHA",
    "MAX_REACH",
    "MIN_ALPHA",
    "decontaminate",
    "estimate_background",
    "nearest_colour",
]
