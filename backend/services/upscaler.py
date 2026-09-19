"""Stage 3 - the upscaler facade.

Upscayl ships an Electron desktop app, but it also bundles a real headless
binary at ``resources/bin/upscayl-bin.exe`` (an ncnn/Vulkan build). This module
is the stable entry point the orchestrator imports; the actual work lives in
:mod:`services.upscale`, split into model discovery, option validation, and the
CLI runner.

The facade exists so callers keep a single, versioned surface:

* :func:`find_cli` / :func:`is_neural_available` - capability probes.
* :func:`upscale_image` - run one upscale, returning an
  :class:`~services.upscale.runner.UpscaleRunResult`.
* :func:`catalog_payload` / :func:`estimate_output` - what the Stage 3 UI needs.

A high-quality Lanczos resample remains as a fallback so Stage 3 is still
functional if the binary is missing, and every result names the backend that
actually ran so the UI never implies a neural upscale that did not happen.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from config import Settings, settings as default_settings
from services.upscale import catalog as _catalog
from services.upscale import runner as _runner
from services.upscale.options import (
    DEFAULT_TARGET_LONG_EDGE,
    RESOLUTION_PRESETS,
    UpscaleOptionError,
    UpscaleOptions,
    default_options,
    estimate_output,
    from_payload,
)
from services.upscale.runner import (
    BACKEND_NEURAL,
    BACKEND_RESAMPLE,
    BACKEND_SKIPPED,
    UpscaleRunResult,
)

__all__ = [
    "BACKEND_NEURAL",
    "BACKEND_RESAMPLE",
    "BACKEND_SKIPPED",
    "DEFAULT_TARGET_LONG_EDGE",
    "RESOLUTION_PRESETS",
    "UpscaleOptionError",
    "UpscaleOptions",
    "UpscaleRunResult",
    "catalog_payload",
    "default_options",
    "estimate_output",
    "find_cli",
    "from_payload",
    "is_neural_available",
    "measure",
    "upscale_image",
]

#: Kept as an alias for callers written against the original module.
UpscaleResult = UpscaleRunResult

ProgressCallback = Callable[[float, str], None]


def find_cli(settings: Settings | None = None) -> str | None:
    """Locate a usable Upscayl CLI binary, or None when only resampling is possible."""
    return _runner.find_cli(settings or default_settings)


def is_neural_available(settings: Settings | None = None) -> bool:
    """True when the neural upscaler can be invoked."""
    return _runner.is_neural_available(settings or default_settings)


def list_models(settings: Settings | None = None, *, refresh: bool = False):
    """Every installed model (both bundled and outsourced)."""
    return _catalog.list_models(settings or default_settings, refresh=refresh)


def catalog_payload(settings: Settings | None = None, *, refresh: bool = False) -> dict:
    """Model list, capacity presets, defaults, and CLI availability for the UI.

    ``refresh`` bypasses the short discovery cache, which the panel uses after
    the operator drops a new model folder into place.
    """
    if refresh:
        _catalog.clear_cache()
    return _catalog.catalog_payload(settings or default_settings)


def measure(file_path: str | Path) -> tuple[int, int] | None:
    """Source ``(width, height)``, or None when the file cannot be read."""
    return _runner.measure(file_path)


def upscale_image(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    options: UpscaleOptions | dict | None = None,
    settings: Settings | None = None,
    on_progress: ProgressCallback | None = None,
) -> UpscaleRunResult:
    """Upscale an image for Stage 3.

    Args:
        file_path: Image to upscale (never modified).
        output_dir: Directory that receives the upscaled copy.
        record_id: Used to name the output file deterministically.
        options: A validated :class:`UpscaleOptions`, a raw request dict, or
            None to use the configured defaults.
        settings: Application settings override.
        on_progress: Called with ``(percent, label)`` during the run.

    Returns:
        An :class:`UpscaleRunResult` naming the backend that actually ran.
    """
    cfg = settings or default_settings

    if isinstance(options, dict):
        resolved: UpscaleOptions | None = from_payload(options, cfg)
    else:
        resolved = options or default_options(cfg)

    # Probe here rather than inside the runner so this module stays the single
    # place that decides which backend a batch will use.
    executable = find_cli(cfg)

    return _runner.upscale_image(
        file_path,
        output_dir,
        record_id,
        options=resolved,
        settings=cfg,
        on_progress=on_progress,
        executable=executable,
    )
