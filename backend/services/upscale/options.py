"""Validated, serialisable options for one Stage 3 upscale run.

The Stage 3 UI is deliberately feature-rich (model, GPU, TTA, capacity, tile
size, JPEG restriction), so this module is the single place that decides which
combinations are *legal* and which defaults are *safe*.

Two rules drive the defaults:

* **Never exceed Adobe's ceiling.** Photos are capped at 100 MP, so a preset
  that would push a small source past that is clamped rather than honoured.
* **Never silently downscale.** If the source is already larger than the chosen
  capacity, the image is passed through at its native size - throwing away
  resolution the contributor already paid for would be worse than a smaller
  than requested long edge.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config import settings as default_settings
from services.upscale import catalog

#: The long-edge presets offered in the UI. 4K is the default because it lands a
#: typical AI source in Adobe's 15-25 MP sweet spot without overshooting the
#: 45 MB file-size ceiling.
RESOLUTION_PRESETS: tuple[tuple[int, str], ...] = (
    (2560, "2K · 2560 px"),
    (3840, "4K · 3840 px"),
    (5120, "5K · 5120 px"),
    (6144, "6K · 6144 px"),
    (7680, "8K · 7680 px"),
)

DEFAULT_TARGET_LONG_EDGE = 3840

#: Tile size. 0 lets ncnn pick automatically, which is the right answer unless
#: the GPU runs out of memory on a very large source.
TILE_AUTO = 0
MIN_TILE_SIZE = 32

#: ``-j load:proc:save`` worker counts. The CLI default is 1:2:2; 2:2:2 is the
#: documented multi-GPU form, so a single GPU stays on the conservative default.
DEFAULT_THREADS = (1, 2, 2)
FAST_THREADS = (2, 2, 2)

#: JPEG quality for the final export. The CLI's ``-c`` is a compression factor
#: (0-100), while the export path uses an ordinary JPEG quality value.
DEFAULT_COMPRESSION = 90

#: Guard rails for the final long edge, independent of the presets.
MIN_TARGET_LONG_EDGE = 1024
MAX_TARGET_LONG_EDGE = 12_000

#: Only JPEG is permitted by Adobe for photos, so this is effectively fixed.
FORCED_FORMAT = "jpg"


class UpscaleOptionError(ValueError):
    """Raised when a caller supplies an unusable option combination."""


def _coerce_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


@dataclass(frozen=True)
class UpscaleOptions:
    """A complete, validated description of one upscale run."""

    model: str
    #: Model scale handed to the CLI's ``-z`` (2, 3, or 4).
    model_scale: int = 4
    #: Target long edge in pixels; the final export is resized to this.
    target_long_edge: int = DEFAULT_TARGET_LONG_EDGE
    #: Vulkan device id. 0 is the dedicated GPU on this machine.
    gpu_id: int = 0
    #: Test-time augmentation - slower, marginally better edges.
    tta: bool = False
    #: Tile size (0 = auto). Lower it when the GPU runs out of memory.
    tile_size: int = TILE_AUTO
    #: Parallel load:proc:save worker counts.
    threads: tuple[int, int, int] = DEFAULT_THREADS
    #: CLI ``-c`` compression factor for the intermediate render.
    compression: int = DEFAULT_COMPRESSION
    #: Embed an sRGB ICC profile in the final JPEG (Adobe requirement).
    embed_srgb: bool = True
    #: Allow the output to be resized *down* to the target when the source is
    #: already larger. Off by default: never throw away resolution silently.
    allow_downscale: bool = False

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "model_scale": self.model_scale,
            "target_long_edge": self.target_long_edge,
            "gpu_id": self.gpu_id,
            "tta": self.tta,
            "tile_size": self.tile_size,
            "threads": list(self.threads),
            "compression": self.compression,
            "embed_srgb": self.embed_srgb,
            "allow_downscale": self.allow_downscale,
            "format": FORCED_FORMAT,
        }

    @property
    def threads_arg(self) -> str:
        return ":".join(str(part) for part in self.threads)


def from_payload(payload: dict | None, settings=None) -> UpscaleOptions:
    """Build validated options from an untrusted request body.

    Unknown models fall back to the configured default rather than erroring:
    the model list is discovered from disk, so a stale UI selection should
    degrade to a working run instead of blocking the batch.
    """
    cfg = settings or default_settings
    data = dict(payload or {})

    available = catalog.list_models(cfg)
    requested = str(data.get("model") or "").strip()
    chosen = catalog.get_model(requested, cfg)
    if chosen is None:
        chosen_name = catalog.default_model_name(available, cfg)
        chosen_scale = next(
            (m.scale for m in available if m.name == chosen_name), 4
        )
    else:
        chosen_name = chosen.name
        chosen_scale = chosen.scale

    if not chosen_name:
        raise UpscaleOptionError(
            "No Upscayl model is installed. Add a .bin/.param pair to "
            "resources/models or Outsourced_models/models."
        )

    model_scale = _coerce_int(data.get("model_scale"), chosen_scale)
    if model_scale not in catalog.VALID_SCALES:
        model_scale = chosen_scale

    configured_target = _coerce_int(
        getattr(cfg, "UPSCAYL_TARGET_LONG_EDGE", None), DEFAULT_TARGET_LONG_EDGE
    )
    target = _coerce_int(data.get("target_long_edge"), configured_target)
    target = max(MIN_TARGET_LONG_EDGE, min(MAX_TARGET_LONG_EDGE, target))

    configured_gpu = _coerce_int(getattr(cfg, "UPSCAYL_GPU_ID", None), 0)
    gpu_id = max(0, _coerce_int(data.get("gpu_id"), configured_gpu))

    tile = _coerce_int(data.get("tile_size"), TILE_AUTO)
    if tile != TILE_AUTO and tile < MIN_TILE_SIZE:
        tile = TILE_AUTO

    threads = data.get("threads")
    if isinstance(threads, (list, tuple)) and len(threads) == 3:
        parsed = tuple(max(1, _coerce_int(part, 2)) for part in threads)
    else:
        parsed = DEFAULT_THREADS

    compression = _coerce_int(data.get("compression"), DEFAULT_COMPRESSION)
    compression = max(0, min(100, compression))

    configured_tta = _coerce_bool(getattr(cfg, "UPSCAYL_TTA", None), False)

    return UpscaleOptions(
        model=chosen_name,
        model_scale=model_scale,
        target_long_edge=target,
        gpu_id=gpu_id,
        tta=_coerce_bool(data.get("tta"), configured_tta),
        tile_size=tile,
        threads=parsed,
        compression=compression,
        embed_srgb=_coerce_bool(
            data.get("embed_srgb"), bool(getattr(cfg, "EMBED_SRGB_PROFILE", True))
        ),
        allow_downscale=_coerce_bool(data.get("allow_downscale"), False),
    )


def default_options(settings=None) -> UpscaleOptions:
    """The options a fresh Stage 3 run uses."""
    return from_payload({}, settings)


def capacity_label(long_edge: int) -> str:
    """Human name for a target long edge, e.g. ``3840`` -> ``"4K"``.

    Adobe's "capacity" vocabulary (2K/4K/8K) is what contributors expect, so a
    preset value is named rather than printed as a raw pixel count. Anything
    between presets falls back to ``"4500px"``.
    """
    for preset, label in RESOLUTION_PRESETS:
        if preset == long_edge:
            # "4K · 3840 px" -> "4K"
            return label.split("·")[0].strip()
    return f"{long_edge}px"


def with_target(options: UpscaleOptions, target_long_edge: int) -> UpscaleOptions:
    """Return a copy aimed at a different long edge (used by the estimator)."""
    clamped = max(MIN_TARGET_LONG_EDGE, min(MAX_TARGET_LONG_EDGE, int(target_long_edge)))
    return replace(options, target_long_edge=clamped)


def estimate_output(
    source_width: int,
    source_height: int,
    options: UpscaleOptions,
    *,
    max_megapixels: float | None = None,
    settings=None,
) -> dict:
    """Predict the output geometry and flag problems before the GPU is used.

    Upscaling is the slowest stage, so a batch that would blow past Adobe's
    megapixel ceiling should be caught in the UI rather than after ten minutes
    of GPU time.
    """
    cfg = settings or default_settings
    ceiling = (
        max_megapixels
        if max_megapixels is not None
        else float(getattr(cfg, "ADOBE_MAX_MEGAPIXELS", 100.0))
    )

    if source_width <= 0 or source_height <= 0:
        return {
            "source_dimensions": [0, 0],
            "target_dimensions": [0, 0],
            "scale": 1.0,
            "will_upscale": False,
            "will_downscale": False,
            "estimated_megapixels": 0.0,
            "exceeds_megapixel_ceiling": False,
            "warnings": ["The source image could not be read."],
        }

    longest = max(source_width, source_height)
    warnings: list[str] = []

    raw_scale = options.target_long_edge / longest
    will_upscale = raw_scale > 1.001
    will_downscale = raw_scale < 0.999

    if will_downscale and not options.allow_downscale:
        # Pass through at native size rather than discarding resolution.
        effective_scale = 1.0
        warnings.append(
            f"The source is already {longest} px on its long edge, which is at or "
            f"above the {options.target_long_edge} px target. It will be kept at "
            "its native size."
        )
    else:
        effective_scale = raw_scale

    target_width = max(1, int(round(source_width * effective_scale)))
    target_height = max(1, int(round(source_height * effective_scale)))
    megapixels = (target_width * target_height) / 1_000_000

    exceeds = megapixels > ceiling
    if exceeds:
        warnings.append(
            f"The estimated output is {megapixels:.1f} MP, above Adobe Stock's "
            f"{ceiling:.0f} MP ceiling. Choose a smaller capacity."
        )

    if will_upscale and options.model_scale == 2 and raw_scale > 2.001:
        warnings.append(
            f"The selected model is {options.model_scale}x but a "
            f"{raw_scale:.1f}x increase was requested; a higher-scale model will "
            "preserve more detail."
        )

    if options.tta:
        warnings.append(
            "TTA mode is enabled: edges improve slightly but each image takes "
            "noticeably longer."
        )

    return {
        "source_dimensions": [source_width, source_height],
        "target_dimensions": [target_width, target_height],
        "scale": round(effective_scale, 4),
        "model_scale": options.model_scale,
        "will_upscale": will_upscale,
        "will_downscale": bool(will_downscale and options.allow_downscale),
        "estimated_megapixels": round(megapixels, 2),
        "exceeds_megapixel_ceiling": exceeds,
        "warnings": warnings,
    }
