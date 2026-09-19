"""Stage 3 upscaling: model discovery, validated options, and the CLI runner.

The package is split so each concern is testable in isolation:

* :mod:`services.upscale.catalog` - which ncnn models are installed.
* :mod:`services.upscale.options` - what a legal, safe configuration looks like.
* :mod:`services.upscale.gpus`    - which Vulkan devices are selectable.
* :mod:`services.upscale.runner`  - driving ``upscayl-bin`` and post-processing.

:mod:`services.upscaler` remains the stable facade the orchestrator imports.
"""

from services.upscale.catalog import (
    UpscaleModel,
    catalog_payload,
    default_model_name,
    get_model,
    list_models,
)
from services.upscale.gpus import (
    GpuDevice,
    default_gpu_id,
    gpus_payload,
    list_gpus,
)
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
    find_cli,
    is_neural_available,
    upscale_image,
)

__all__ = [
    "BACKEND_NEURAL",
    "BACKEND_RESAMPLE",
    "BACKEND_SKIPPED",
    "DEFAULT_TARGET_LONG_EDGE",
    "RESOLUTION_PRESETS",
    "GpuDevice",
    "UpscaleModel",
    "UpscaleOptionError",
    "UpscaleOptions",
    "UpscaleRunResult",
    "catalog_payload",
    "default_gpu_id",
    "default_model_name",
    "default_options",
    "estimate_output",
    "find_cli",
    "from_payload",
    "get_model",
    "gpus_payload",
    "is_neural_available",
    "list_gpus",
    "list_models",
    "upscale_image",
]
