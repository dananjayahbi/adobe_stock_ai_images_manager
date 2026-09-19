"""Model catalogue for the bundled Upscayl ncnn binaries.

Upscayl keeps its weights in two places: the seven models shipped with the app
(``resources/models``) and any user-supplied weights dropped into
``Outsourced_models/models``. Both are plain ncnn pairs - a ``.bin`` weight blob
beside a ``.param`` network description - and a model is only usable when *both*
halves are present.

Nothing here hard-codes the model list. The catalogue is discovered from disk,
so dropping a new ``.bin``/``.param`` pair into either folder makes it
selectable in the UI without a code change; the curated descriptions below are
purely cosmetic and fall back to the raw model name.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from config import settings as default_settings
from services.upscale.options import (
    MAX_TARGET_LONG_EDGE,
    MIN_TILE_SIZE,
    MIN_TARGET_LONG_EDGE,
)

logger = logging.getLogger(__name__)

#: Model sources, reported to the UI so it can group the picker.
SOURCE_BUNDLED = "bundled"
SOURCE_OUTSOURCED = "outsourced"
SOURCE_CUSTOM = "custom"

#: How long a directory scan is reused. Long enough to make a batch of upscales
#: cheap, short enough that dropping in a new model shows up on the next click.
_CACHE_TTL_SECONDS = 5.0

#: Model scales the CLI accepts (``-z``).
VALID_SCALES = (2, 3, 4)

#: Curated blurbs. Keyed by lower-cased model name; unknown models fall back to
#: a description derived from their filename.
_DESCRIPTIONS: dict[str, str] = {
    # --- bundled with Upscayl ------------------------------------------------
    "upscayl-standard-4x": (
        "Upscayl's default general-purpose model. Balanced detail and speed; a "
        "safe choice for most photographic content."
    ),
    "upscayl-lite-4x": (
        "Faster, lighter sibling of the standard model. Slightly less fine "
        "detail - useful for very large batches."
    ),
    "high-fidelity-4x": (
        "Conservative upscale that preserves the source's character. Least "
        "likely to invent texture, which suits already-sharp AI output."
    ),
    "ultramix-balanced-4x": (
        "Blends several training sets for a balanced photographic result."
    ),
    "ultrasharp-4x": (
        "Aggressively restores micro-contrast. Can oversharpen - always check "
        "edges at 100% before uploading."
    ),
    "remacri-4x": (
        "Strong on natural texture and foliage, but can add visible grain."
    ),
    "digital-art-4x": (
        "Tuned for illustration and digital art rather than photographs."
    ),
    # --- outsourced ----------------------------------------------------------
    "4xnomos8ksc": (
        "Nomos 8K self-calibrated. Excellent all-round photographic model with "
        "strong fine-texture recovery."
    ),
    "4xlsdir": (
        "Large-scale dataset model. Clean, natural results on photographs."
    ),
    "4xlsdirplusc": (
        "LSDIR plus a contrast-aware pass; slightly crisper than plain LSDIR."
    ),
    "4xlsdircompactc3": (
        "Compact LSDIR variant - noticeably faster, marginally softer."
    ),
    "4xhfa2k": "High-frequency-aware model; good for detailed surfaces.",
    "4x_nmkd-siax_200k": "NMKD Siax. Sharp and well suited to landscapes and architecture.",
    "4x_nmkd-superscale-sp_178000_g": "NMKD Superscale. Balanced, widely used general model.",
    "realesr-animevideov3-x2": "Real-ESRGAN anime video model at 2x. For illustration, not photography.",
    "realesr-animevideov3-x3": "Real-ESRGAN anime video model at 3x. For illustration, not photography.",
    "realesr-animevideov3-x4": "Real-ESRGAN anime video model at 4x. For illustration, not photography.",
    "realesrgan_general_x4_v3": (
        "Real-ESRGAN v3 general. Reliable, well-tested photographic model."
    ),
    "realesrgan_general_wdn_x4_v3": (
        "Real-ESRGAN v3 with denoise. Reduces noise while upscaling - handy for "
        "grainy AI output."
    ),
    "uniscale_restore": "Restoration model; repair-oriented rather than a pure upscaler.",
    "unknown-2.0.1": "Unidentified model. Scale is inferred from the filename.",
}

#: Models offered as a highlighted shortcut in the UI. These are the general
#: photographic models that consistently score well on the acceptance engine.
_RECOMMENDED = frozenset(
    {
        "4xnomos8ksc",
        "4xlsdir",
        "realesrgan_general_x4_v3",
        "upscayl-standard-4x",
        "high-fidelity-4x",
    }
)

#: Preference order used when the configured default model is not installed.
_FALLBACK_ORDER = (
    "4xNomos8kSC",
    "upscayl-standard-4x",
    "RealESRGAN_General_x4_v3",
    "4xLSDIR",
)

_SCALE_PATTERNS = (
    re.compile(r"(?i)^(\d)x"),  # 4xNomos8kSC, 2xSomething
    re.compile(r"(?i)[-_]x(\d)$"),  # realesr-animevideov3-x2
    re.compile(r"(?i)[-_](\d)x$"),  # digital-art-4x
)

#: Directory listings are re-read at most once per TTL window.
_cache: tuple[float, tuple[str, ...], list["UpscaleModel"]] | None = None


@dataclass(frozen=True)
class UpscaleModel:
    """One usable ncnn model (a ``.bin``/``.param`` pair on disk)."""

    name: str
    label: str
    scale: int
    source: str
    description: str
    directory: str
    recommended: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "scale": self.scale,
            "source": self.source,
            "description": self.description,
            "recommended": self.recommended,
        }


def _infer_scale(name: str) -> int:
    """Best-effort scale detection from a model filename.

    Upscayl's own models are all 4x, but the outsourced set includes 2x and 3x
    variants whose names encode the factor. Getting this wrong would make the
    CLI emit the wrong output size, so the patterns are deliberately narrow.
    """
    for pattern in _SCALE_PATTERNS:
        match = pattern.search(name)
        if match:
            scale = int(match.group(1))
            if scale in VALID_SCALES:
                return scale
    return 4


def _label_for(name: str) -> str:
    """Turn ``4x_NMKD-Superscale-SP_178000_G`` into a readable label."""
    cleaned = re.sub(r"[_]+", " ", name).replace("-", " ").strip()
    return re.sub(r"\s+", " ", cleaned)


def _describe(name: str) -> str:
    described = _DESCRIPTIONS.get(name.lower())
    if described:
        return described
    return "No description available for this model."


def model_directories(settings=None) -> list[tuple[str, Path]]:
    """Return ``(source, directory)`` pairs to scan, in display order."""
    cfg = settings or default_settings
    app_dir = Path(getattr(cfg, "UPSCAYL_APP_DIR", ""))

    roots: list[tuple[str, Path]] = [
        (SOURCE_BUNDLED, app_dir / "resources" / "models"),
        (SOURCE_OUTSOURCED, app_dir / "Outsourced_models" / "models"),
    ]

    for extra in getattr(cfg, "UPSCAYL_MODEL_DIRS", None) or []:
        roots.append((SOURCE_CUSTOM, Path(extra)))

    # Preserve order while dropping duplicates and blanks.
    seen: set[str] = set()
    unique: list[tuple[str, Path]] = []
    for source, directory in roots:
        key = str(directory).lower()
        if not str(directory) or key in seen:
            continue
        seen.add(key)
        unique.append((source, directory))
    return unique


def _scan(settings=None) -> list[UpscaleModel]:
    """Discover every usable model pair across all model roots."""
    models: list[UpscaleModel] = []
    seen_names: set[str] = set()

    for source, directory in model_directories(settings):
        if not directory.is_dir():
            logger.debug("Upscayl model directory not present: %s", directory)
            continue

        try:
            params = {path.stem for path in directory.glob("*.param")}
            bins = {path.stem for path in directory.glob("*.bin")}
        except OSError:
            logger.warning("Could not list Upscayl models in %s", directory)
            continue

        # A model is only usable when both halves exist.
        for name in sorted(params & bins, key=str.lower):
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            models.append(
                UpscaleModel(
                    name=name,
                    label=_label_for(name),
                    scale=_infer_scale(name),
                    source=source,
                    description=_describe(name),
                    directory=str(directory),
                    recommended=name.lower() in _RECOMMENDED,
                )
            )

    return models


def list_models(settings=None, *, refresh: bool = False) -> list[UpscaleModel]:
    """Every usable model, cached briefly to keep batch runs cheap."""
    global _cache

    key = tuple(str(directory) for _, directory in model_directories(settings))
    now = time.monotonic()

    if (
        not refresh
        and _cache is not None
        and _cache[1] == key
        and (now - _cache[0]) < _CACHE_TTL_SECONDS
    ):
        return list(_cache[2])

    models = _scan(settings)
    _cache = (now, key, models)
    return list(models)


def clear_cache() -> None:
    """Drop the cached scan (used by tests and after adding a model folder)."""
    global _cache
    _cache = None


def get_model(name: str | None, settings=None) -> UpscaleModel | None:
    """Look up one model by exact name, case-insensitively."""
    if not name:
        return None
    wanted = name.strip().lower()
    for model in list_models(settings):
        if model.name.lower() == wanted:
            return model
    return None


def default_model_name(models: list[UpscaleModel] | None = None, settings=None) -> str:
    """Resolve the default model, degrading gracefully when one is missing.

    The configured name wins when it is installed. Otherwise the first entry of
    :data:`_FALLBACK_ORDER` that exists is used, so a checkout without the
    ``Outsourced_models`` folder still upscales instead of failing.
    """
    cfg = settings or default_settings
    available = models if models is not None else list_models(cfg)
    by_name = {model.name.lower(): model.name for model in available}

    configured = str(getattr(cfg, "UPSCAYL_MODEL", "") or "").strip()
    if configured and configured.lower() in by_name:
        return by_name[configured.lower()]
    if configured:
        logger.info(
            "Configured Upscayl model '%s' is not installed; choosing a fallback.",
            configured,
        )

    for candidate in _FALLBACK_ORDER:
        if candidate.lower() in by_name:
            return by_name[candidate.lower()]

    return available[0].name if available else ""


def catalog_payload(settings=None) -> dict:
    """Full picker payload for the Stage 3 UI.

    Beyond the model list this carries the capacity presets, the configured
    defaults, and whether a neural backend is actually reachable - the panel
    needs all of it to render honestly (and to warn instead of pretending).
    """
    from services.upscale import runner as _runner
    from services.upscale.options import (
        DEFAULT_COMPRESSION,
        DEFAULT_TARGET_LONG_EDGE,
        RESOLUTION_PRESETS,
        TILE_AUTO,
        default_options,
    )

    cfg = settings or default_settings
    models = list_models(cfg)
    default_name = default_model_name(models, cfg)
    configured_target = int(
        getattr(cfg, "UPSCAYL_TARGET_LONG_EDGE", DEFAULT_TARGET_LONG_EDGE)
        or DEFAULT_TARGET_LONG_EDGE
    )

    defaults = default_options(cfg)
    executable = _runner.find_cli(cfg)

    return {
        "models": [model.to_dict() for model in models],
        "default_model": default_name,
        "sources": {
            SOURCE_BUNDLED: "Bundled with Upscayl",
            SOURCE_OUTSOURCED: "Outsourced models",
            SOURCE_CUSTOM: "Custom model folders",
        },
        "directories": [
            {"source": source, "path": str(directory), "exists": directory.is_dir()}
            for source, directory in model_directories(cfg)
        ],
        "resolutions": [
            {"long_edge": edge, "label": label, "default": edge == configured_target}
            for edge, label in RESOLUTION_PRESETS
        ],
        "defaults": {
            "target_long_edge": configured_target,
            "gpu_id": defaults.gpu_id,
            "model_scale": defaults.model_scale,
            "tta": defaults.tta,
            "tile_size": defaults.tile_size or TILE_AUTO,
            "compression": defaults.compression or DEFAULT_COMPRESSION,
            "embed_srgb": defaults.embed_srgb,
            "allow_downscale": defaults.allow_downscale,
        },
        "neural_available": executable is not None,
        "executable": executable,
        "presets": {
            "tile_auto": TILE_AUTO,
            "min_tile_size": MIN_TILE_SIZE,
            "max_target_long_edge": MAX_TARGET_LONG_EDGE,
            "min_target_long_edge": MIN_TARGET_LONG_EDGE,
            "forced_format": "jpg",
        },
    }
