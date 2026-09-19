"""Stage 3 - the upscaler.

Upscayl ships as an Electron desktop app (``backend/upscayl-2.15.0/Upscayl.exe``)
with its model weights under ``resources/models``. It is not a headless CLI, so
this module is deliberately staged in two halves:

* :func:`find_cli` probes for a real CLI binary or a configured
  ``UPSCAYL_EXE`` path and reports whether one is usable.
* :func:`upscale_image` performs a high-quality resample as a *fallback* so
  Stage 3 is functional today, and transparently switches to the neural
  upscaler once a CLI is available.

The caller always receives a :class:`UpscaleResult` describing which backend
ran, so the UI can label the output honestly instead of implying a neural
upscale that never happened.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

#: Backend identifiers reported back to the UI.
BACKEND_NEURAL = "upscayl"
BACKEND_RESAMPLE = "lanczos-resample"
BACKEND_SKIPPED = "skipped"

#: Adobe's practical sweet spot for AI stock photos is 15-25 MP; beyond that
#: files grow past the 45 MB ceiling for no licensing benefit.
TARGET_MAX_MEGAPIXELS = 25.0


@dataclass
class UpscaleResult:
    """Outcome of one upscale attempt."""

    success: bool
    output_path: str | None = None
    backend: str = BACKEND_SKIPPED
    scale: float = 1.0
    source_dimensions: tuple[int, int] = (0, 0)
    output_dimensions: tuple[int, int] = (0, 0)
    reason: str = ""

    @property
    def source_megapixels(self) -> float:
        width, height = self.source_dimensions
        return (width * height) / 1_000_000

    @property
    def output_megapixels(self) -> float:
        width, height = self.output_dimensions
        return (width * height) / 1_000_000

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "backend": self.backend,
            "scale": round(self.scale, 3),
            "source_dimensions": list(self.source_dimensions),
            "output_dimensions": list(self.output_dimensions),
            "source_megapixels": round(self.source_megapixels, 2),
            "output_megapixels": round(self.output_megapixels, 2),
            "reason": self.reason,
        }


def find_cli(settings: Settings | None = None) -> str | None:
    """Locate a usable Upscayl executable.

    Returns the executable path, or None when only the desktop app is present
    (in which case :func:`upscale_image` falls back to resampling).
    """
    cfg = settings or default_settings

    configured = getattr(cfg, "UPSCAYL_EXE", None)
    if configured:
        candidate = Path(configured)
        if candidate.exists() and candidate.is_file():
            # The Electron GUI cannot accept CLI flags; a bundled CLI would.
            if candidate.name.lower() not in ("upscayl.exe",):
                return str(candidate)
            logger.info(
                "Found the Upscayl desktop app at %s; no headless CLI is bundled, "
                "so Stage 3 will use high-quality resampling.",
                candidate,
            )

    for name in ("upscayl-bin", "upscayl-cli", "upscayl-ncnn", "realesrgan-ncnn-vulkan"):
        found = shutil.which(name)
        if found:
            return found

    return None


def is_neural_available(settings: Settings | None = None) -> bool:
    """True when a neural upscaler CLI can be invoked."""
    return find_cli(settings) is not None


def _read_dimensions(path: Path) -> tuple[int, int]:
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return (0, 0)
    height, width = image.shape[:2]
    return (width, height)


def _target_scale(
    width: int, height: int, requested_scale: int
) -> float:
    """Pick the smallest scale that clears the megapixel target.

    Upscaling a 20 MP image by 4x would produce a 320 MP monster that fails the
    resolution ceiling and the file-size cap, so the scale is clamped.
    """
    current_mp = (width * height) / 1_000_000
    if current_mp <= 0:
        return 1.0

    # Never exceed the 25 MP practical ceiling.
    ceiling_scale = float(np.sqrt(TARGET_MAX_MEGAPIXELS / current_mp))
    return float(max(1.0, min(float(requested_scale), ceiling_scale)))


def _resample(image: np.ndarray, scale: float) -> np.ndarray:
    """High-quality Lanczos resample with a light post-sharpen.

    Lanczos alone leaves upscaled edges slightly soft, so a restrained unsharp
    pass restores acutance without the halos a stronger kernel would create.
    """
    height, width = image.shape[:2]
    target = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    resized = cv2.resize(image, target, interpolation=cv2.INTER_LANCZOS4)

    blurred = cv2.GaussianBlur(resized, (0, 0), 1.0)
    sharpened = cv2.addWeighted(resized, 1.35, blurred, -0.35, 0)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def upscale_image(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    settings: Settings | None = None,
) -> UpscaleResult:
    """Upscale an image for Stage 3.

    Uses the neural CLI when one is available and falls back to a Lanczos
    resample otherwise. Images already at or above the megapixel target are
    passed through untouched.

    Args:
        file_path: Image to upscale (never modified).
        output_dir: Directory that receives the upscaled copy.
        record_id: Used to name the output file deterministically.
        settings: Application settings override.

    Returns:
        An :class:`UpscaleResult` naming the backend that actually ran.
    """
    cfg = settings or default_settings
    source = Path(file_path)
    if not source.exists():
        return UpscaleResult(False, reason=f"File not found: {file_path}")

    width, height = _read_dimensions(source)
    if width == 0:
        return UpscaleResult(False, reason=f"Could not decode image: {file_path}")

    requested_scale = int(getattr(cfg, "UPSCAYL_SCALE", 4) or 4)
    scale = _target_scale(width, height, requested_scale)

    if scale <= 1.001:
        return UpscaleResult(
            True,
            output_path=str(source),
            backend=BACKEND_SKIPPED,
            scale=1.0,
            source_dimensions=(width, height),
            output_dimensions=(width, height),
            reason="Image already meets the megapixel target; upscaling skipped.",
        )

    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    destination = output_dir_path / f"{record_id}-upscaled.jpg"

    cli = find_cli(cfg)
    if cli:
        result = _run_neural(cli, source, destination, cfg)
        if result.success:
            result.source_dimensions = (width, height)
            result.output_dimensions = _read_dimensions(destination)
            return result
        logger.warning(
            "Neural upscale failed (%s); falling back to resampling.", result.reason
        )

    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        return UpscaleResult(False, reason=f"Could not decode image: {file_path}")

    upscaled = _resample(image, scale)
    quality = int(getattr(cfg, "EXPORT_JPEG_QUALITY", 95))
    try:
        written = cv2.imwrite(
            str(destination),
            upscaled,
            [cv2.IMWRITE_JPEG_QUALITY, quality, cv2.IMWRITE_JPEG_CHROMA_QUALITY, 100],
        )
    except Exception:  # noqa: BLE001 - disk errors must not crash the batch
        logger.exception("Failed to write upscaled image %s", destination)
        written = False

    if not written:
        return UpscaleResult(False, reason="Failed to write the upscaled image.")

    return UpscaleResult(
        True,
        output_path=str(destination),
        backend=BACKEND_RESAMPLE,
        scale=scale,
        source_dimensions=(width, height),
        output_dimensions=_read_dimensions(destination),
        reason=(
            "Upscaled with high-quality Lanczos resampling. Install an Upscayl CLI "
            "to enable neural upscaling."
        ),
    )


def _run_neural(
    executable: str, source: Path, destination: Path, cfg: Settings
) -> UpscaleResult:
    """Invoke a neural upscaler CLI and return its outcome."""
    model = str(getattr(cfg, "UPSCAYL_MODEL", "upscayl-standard-4x"))
    timeout = int(getattr(cfg, "UPSCAYL_TIMEOUT_SECONDS", 600))

    command = [
        executable,
        "-i",
        str(source),
        "-o",
        str(destination),
        "-m",
        model,
    ]

    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return UpscaleResult(
            False, backend=BACKEND_NEURAL, reason=f"Upscaler timed out after {timeout}s."
        )
    except OSError as exc:
        return UpscaleResult(
            False, backend=BACKEND_NEURAL, reason=f"Could not run upscaler: {exc}"
        )

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[:300]
        return UpscaleResult(
            False,
            backend=BACKEND_NEURAL,
            reason=f"Upscaler exited with {completed.returncode}: {detail}",
        )

    if not destination.exists():
        return UpscaleResult(
            False, backend=BACKEND_NEURAL, reason="Upscaler produced no output file."
        )

    return UpscaleResult(
        True,
        output_path=str(destination),
        backend=BACKEND_NEURAL,
        scale=float(getattr(cfg, "UPSCAYL_SCALE", 4) or 4),
        reason=f"Upscaled with the neural model '{model}'.",
    )
