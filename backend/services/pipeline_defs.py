"""Step catalog — the single source of truth for batch pipeline v2 steps.

A batch declares *which steps run*; this module owns which steps exist, their
canonical order, which media type they belong to, their default configuration,
and their validation. The API, the pipeline runner, and the frontend (via
``GET /api/batches/steps``) all read from here, so the three cannot drift.

Design rules
------------
* **Canonical order is fixed.** The operator picks *which* steps run; the runner
  always executes them in this order. It starts with ``upscale`` because a
  super-resolution pass after masking resamples the alpha channel with a
  bicubic blur and leaves stair-stepped, haloed edges — the fastest way to fail
  a 100% crop inspection. So: raise the RGB resolution first, *then* mask it at
  that resolution. ``bg_remove`` precedes OCR so OCR inspects the kept object
  rather than the background it is about to throw away, and ``metadata`` comes
  last because it needs the final image.
* **Configs are validated per step, leniently.** Unknown keys are dropped and
  missing keys fall back to defaults, so a saved profile from an older version
  never crashes a run.
* Steps are plain dicts (JSON-serialisable) — no dataclasses leak into the API.
"""

from __future__ import annotations

from config import Settings, settings as default_settings

#: Canonical step order. The runner sorts picked steps by this list.
STEP_ORDER: tuple[str, ...] = (
    "upscale",
    "bg_remove",
    "ocr",
    "refine",
    "compatibility",
    "metadata",
)

#: Which media types may pick a step.
STEP_MEDIA_TYPES: dict[str, tuple[str, ...]] = {
    "bg_remove": ("png",),
    "ocr": ("raster", "png"),
    "upscale": ("raster", "png"),
    "refine": ("raster",),        # writes JPEG — photo pipeline only
    "compatibility": ("raster",),  # 80% photo gate — photo pipeline only
    "metadata": ("raster", "png"),
}

#: Human labels and one-line descriptions for the step picker.
STEP_META: dict[str, dict[str, str]] = {
    "bg_remove": {
        "label": "Background removal",
        "description": (
            "Segments the object, rebuilds the boundary with a sub-pixel matte, "
            "strips backdrop colour from the edge, sanitises the alpha, then "
            "audits the cut-out on both white and black."
        ),
    },
    "ocr": {
        "label": "OCR scan",
        "description": "Scans for embedded text. Text found removes the image from the batch.",
    },
    "upscale": {
        "label": "Upscale",
        "description": (
            "Raises resolution to the Adobe Stock megapixel target. Runs first, "
            "so background removal masks the high-res pixels rather than a "
            "resampled copy of them."
        ),
    },
    "refine": {
        "label": "Refine",
        "description": "Applies corrective adjustments until the acceptance score clears 80%.",
    },
    "compatibility": {
        "label": "Acceptance QC",
        "description": "Runs the full acceptance algorithm and gates at the 80% threshold.",
    },
    "metadata": {
        "label": "Metadata & keywords",
        "description": "Generates titles, descriptions, keywords, and the category.",
    },
}

#: Default config per step. Doubles as the declared config schema.
def default_step_config(key: str, cfg: Settings | None = None) -> dict:
    """Return the default configuration for one step."""
    settings = cfg or default_settings
    if key == "bg_remove":
        return {
            # Segmentation runs on the CUDA execution provider when the local
            # onnxruntime exposes it; flip this to force the CPU path.
            "gpu": True,
            # BiRefNet-general: bilateral-reference segmentation that keeps
            # hair-thin antennae and root hairs where ISNet/U²Net sever them.
            "model": "birefnet-general",
            # Sub-pixel matting on the auto-trimap: guided (offline, always
            # available) or vitmatte (opt-in, needs transformers).
            "matting": "guided",
            # Un-blend backdrop colour out of the soft edge.
            "defringe": True,
            # Choke, hard cutoff and stray-island removal.
            "sanitize": True,
            "edge_check": True,
        }
    if key == "upscale":
        # Mirror the Stage 3 defaults the operator already trusts.
        return {
            "model": "4xNomos8kSC",
            "target_long_edge": 3840,
            "gpu_id": 0,
            "tta": False,
        }
    if key in ("refine", "compatibility"):
        return {"use_semantic": True}
    if key == "metadata":
        return {"delay_seconds": float(getattr(settings, "METADATA_CALL_DELAY_SECONDS", 2.0))}
    return {}


def available_steps(media_type: str) -> list[str]:
    """Steps pickable for a media type, in canonical order."""
    return [key for key in STEP_ORDER if media_type in STEP_MEDIA_TYPES.get(key, ())]


def step_payload(key: str, cfg: Settings | None = None) -> dict:
    """Full step descriptor for the API: key, label, description, defaults."""
    meta = STEP_META[key]
    return {
        "key": key,
        "label": meta["label"],
        "description": meta["description"],
        "media_types": list(STEP_MEDIA_TYPES[key]),
        "default_config": default_step_config(key, cfg),
    }


def catalog_payload(media_type: str | None = None, cfg: Settings | None = None) -> list[dict]:
    """The step catalog, optionally filtered to one media type."""
    keys = available_steps(media_type) if media_type else list(STEP_ORDER)
    return [step_payload(key, cfg) for key in keys]


def normalise_steps(steps: list, media_type: str, cfg: Settings | None = None) -> list[dict]:
    """Validate a requested step list for a media type.

    * drops steps not pickable by ``media_type`` or unknown to the catalog
    * merges each step's config over its defaults (unknown keys dropped)
    * sorts into canonical order

    Raises ``ValueError`` with a readable message when nothing valid remains.
    """
    allowed = set(available_steps(media_type))
    by_key: dict[str, dict] = {}
    for entry in steps or []:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        if key not in allowed or key in by_key:
            continue
        raw_config = entry.get("config") or {}
        defaults = default_step_config(key, cfg)
        config = {
            k: raw_config[k] for k in defaults if isinstance(raw_config, dict) and k in raw_config
        }
        merged = {**defaults, **config}
        by_key[key] = {"key": key, "config": merged}

    ordered = [by_key[key] for key in STEP_ORDER if key in by_key]
    if not ordered:
        raise ValueError(
            f"No valid steps for media type '{media_type}'. "
            f"Allowed: {', '.join(available_steps(media_type))}."
        )
    return ordered
