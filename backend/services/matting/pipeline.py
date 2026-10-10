"""The stock-grade cut-out pipeline: refine → defringe → sanitize.

One entry point that a caller (the batch runner, a test, a notebook) can hand
an RGBA array to and get back a hardened RGBA array plus a per-stage report.
Stages are individually switchable so a batch config can turn any of them off
without forking the code path.
"""

from __future__ import annotations

import numpy as np

from .defringe import decontaminate
from .refine import DEFAULT_RAMP, METHODS, refine_alpha
from .sanitize import (
    DEFAULT_CHOKE_PX,
    DEFAULT_HARD_CUTOFF,
    DEFAULT_MIN_ISLAND_PX,
    remove_islands,
    sanitize_alpha,
)

#: Defaults for every knob the pipeline understands.
DEFAULT_CONFIG: dict = {
    "matting": "guided",
    "defringe": True,
    "sanitize": True,
    "trimap_radius": 4,
    "ramp": DEFAULT_RAMP,
    "choke_px": DEFAULT_CHOKE_PX,
    "hard_cutoff": DEFAULT_HARD_CUTOFF,
    "min_island_px": DEFAULT_MIN_ISLAND_PX,
    "defringe_strength": 1.0,
}


def resolve_config(config: dict | None) -> dict:
    """Merge a (possibly partial, possibly old) step config over the defaults.

    Unknown keys are ignored and missing ones fall back, exactly like
    ``pipeline_defs.normalise_steps`` does for the step itself — so a profile
    saved before this pipeline existed still runs.
    """
    merged = dict(DEFAULT_CONFIG)
    for key, value in (config or {}).items():
        if key in merged and value is not None:
            merged[key] = value
    if merged["matting"] not in METHODS:
        merged["matting"] = DEFAULT_CONFIG["matting"]
    return merged


def refine_cutout(rgba: np.ndarray, config: dict | None = None) -> tuple[np.ndarray, dict]:
    """Run the post-segmentation stages over one RGBA array.

    Returns ``(rgba, stages)`` where ``stages`` records what each stage
    actually did — it lands verbatim in ``record.stage_details`` so the UI can
    show *why* a cut-out is stock-grade rather than just that it ran.
    """
    arr = np.asarray(rgba)
    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ValueError("refine_cutout expects an HxWx4 RGBA array")

    opts = resolve_config(config)
    stages: dict = {"config": dict(opts)}

    rgb = arr[..., :3].copy()
    alpha = arr[..., 3].astype(np.float64)

    # Strip stray islands *before* matting: a dust speck inside the trimap's
    # foreground would be smoothed by the refiner into a soft blob that is too
    # big for the post-matte island filter to catch afterwards.
    islands_before = island_px_before = 0
    if opts["sanitize"] and int(opts["min_island_px"]) > 0:
        alpha_u8 = np.clip(np.round(alpha), 0, 255).astype(np.uint8)
        _, islands_before, island_px_before = remove_islands(
            alpha_u8, int(opts["min_island_px"])
        )
        alpha = alpha_u8.astype(np.float64)

    alpha, matting_note = refine_alpha(
        rgb,
        alpha,
        method=str(opts["matting"]),
        trimap_radius=int(opts["trimap_radius"]),
        ramp=float(opts["ramp"]),
    )
    stages["matting"] = {"method": str(opts["matting"]), "detail": matting_note}
    out = np.dstack([rgb, np.clip(np.round(alpha), 0, 255).astype(np.uint8)])

    if opts["defringe"]:
        out, notes = decontaminate(out, strength=float(opts["defringe_strength"]))
        stages["defringe"] = notes
    else:
        stages["defringe"] = {"applied": False, "reason": "disabled"}

    if opts["sanitize"]:
        out, stats = sanitize_alpha(
            out,
            choke_px=float(opts["choke_px"]),
            hard_cutoff=int(opts["hard_cutoff"]),
            min_island_px=int(opts["min_island_px"]),
        )
        stats["islands_removed_pre_matting"] = islands_before
        stats["island_pixels_pre_matting"] = island_px_before
        stages["sanitize"] = stats
    else:
        stages["sanitize"] = {"applied": False, "reason": "disabled"}

    return out, stages


__all__ = ["DEFAULT_CONFIG", "refine_cutout", "resolve_config"]
