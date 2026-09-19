"""Drives the bundled Upscayl ncnn binary for one image.

Three behaviours in this module were discovered by probing the real binary and
would be easy to get wrong:

1. **The exit code is 1 even on success.** ``upscayl-bin`` prints
   "Upscayled Successfully!" and then exits 1. Success is therefore decided by
   the output file existing and decoding, never by ``returncode``.
2. **``-v`` streams ``NN.NN%`` progress on stdout.** That is what makes a real
   progress bar possible instead of a spinner, so stdout is read line by line
   rather than collected at the end.
3. **The CLI writes an untagged JPEG.** Adobe requires an sRGB profile, so the
   neural render is written to a lossless intermediate and then handed to
   :mod:`services.srgb_profile`, which resizes to the exact target long edge and
   embeds the profile. Going through PNG avoids a second generation of JPEG
   artefacts.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from config import Settings, settings as default_settings
from services.srgb_profile import has_srgb_profile, write_srgb_jpeg
from services.upscale import catalog
from services.upscale.options import UpscaleOptions, TILE_AUTO

logger = logging.getLogger(__name__)

#: Backend identifiers reported back to the UI.
BACKEND_NEURAL = "upscayl"
BACKEND_RESAMPLE = "lanczos-resample"
BACKEND_SKIPPED = "skipped"

#: Where the CLI lives inside the bundled app.
CLI_RELATIVE_PATH = Path("resources") / "bin" / "upscayl-bin.exe"

#: Alternative binary names, for non-Windows bundles or a PATH install.
CLI_FALLBACK_NAMES = ("upscayl-bin", "upscayl-ncnn", "realesrgan-ncnn-vulkan")

#: Launchers that must never be used as a CLI. These are the Electron GUI
#: entrypoints: they sit at the app root, ignore every flag we pass, and would
#: report a fake success while nothing was upscaled.
CLI_REJECTED_NAMES = frozenset({"upscayl.exe", "upscayl"})

#: At most this many neural passes are chained. An 8K target from a ~1 MP source
#: needs two; a third pass would cost minutes for no visible gain.
MAX_CLI_PASSES = 3

#: Matches the CLI's verbose progress lines, e.g. ``33.33%``.
_PROGRESS_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")

#: Lines worth surfacing when a run fails; everything else is Vulkan noise.
#: The CLI logs benign warnings through the same stream, so these are collected
#: as diagnostics rather than treated as failure - they only reach the operator
#: when no output file appeared.
_ERROR_HINTS = (
    "error",
    "failed",
    "invalid",
    "cannot",
    "could not",
    "unable",
    "not found",
    "no such",
)

ProgressCallback = Callable[[float, str], None]

#: Distinguishes "resolve the executable yourself" from an explicit ``None``,
#: which means "no CLI is available, go straight to the resample fallback".
#: The facade relies on this so a caller that has already probed for the binary
#: (or a test that has stubbed the probe) keeps control of the decision.
_AUTO = object()


@dataclass
class UpscaleRunResult:
    """Outcome of one upscale attempt.

    The first nine fields mirror the original :class:`UpscaleResult` so existing
    callers and the frontend ``UpscaleDetail`` type keep working unchanged.
    """

    success: bool
    output_path: str | None = None
    backend: str = BACKEND_SKIPPED
    scale: float = 1.0
    source_dimensions: tuple[int, int] = (0, 0)
    output_dimensions: tuple[int, int] = (0, 0)
    reason: str = ""
    # --- added by the feature-full upscaler -------------------------------- #
    model: str = ""
    model_scale: int = 4
    gpu_id: int = 0
    tta: bool = False
    tile_size: int = TILE_AUTO
    passes: int = 0
    target_long_edge: int = 0
    duration_seconds: float = 0.0
    srgb_embedded: bool = False
    warnings: list[str] = field(default_factory=list)
    command: list[str] = field(default_factory=list)

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
            "model": self.model,
            "model_scale": self.model_scale,
            "gpu_id": self.gpu_id,
            "tta": self.tta,
            "tile_size": self.tile_size,
            "passes": self.passes,
            "target_long_edge": self.target_long_edge,
            "duration_seconds": round(self.duration_seconds, 2),
            "srgb_embedded": self.srgb_embedded,
            "warnings": list(self.warnings),
        }


def find_cli(settings: Settings | None = None) -> str | None:
    """Locate a usable Upscayl CLI binary.

    Prefers the binary bundled with the app under ``resources/bin`` and falls
    back to a ``UPSCAYL_EXE`` override and then to PATH.

    The Electron launcher (``Upscayl.exe``) is explicitly rejected: it exists at
    the app root, ignores CLI flags, and silently opening a GUI would look like
    a successful upscale that never happened.
    """
    cfg = settings or default_settings

    configured = getattr(cfg, "UPSCAYL_EXE", None)
    if configured:
        candidate = Path(configured)
        # Accept either the binary itself or the app folder that holds it.
        for path in (candidate, candidate / CLI_RELATIVE_PATH):
            if path.is_file() and path.name.lower() not in CLI_REJECTED_NAMES:
                return str(path)

    app_dir = getattr(cfg, "UPSCAYL_APP_DIR", None)
    if app_dir:
        bundled = Path(app_dir) / CLI_RELATIVE_PATH
        if bundled.is_file():
            return str(bundled)

    for name in CLI_FALLBACK_NAMES:
        found = shutil.which(name)
        if found:
            return found

    return None


def is_neural_available(settings: Settings | None = None) -> bool:
    """True when a neural upscaler CLI can be invoked."""
    return find_cli(settings) is not None


def _read_image(path: Path) -> np.ndarray | None:
    try:
        return cv2.imread(str(path), cv2.IMREAD_COLOR)
    except Exception:  # noqa: BLE001 - a corrupt file must not crash the batch
        logger.exception("Could not read image %s", path)
        return None


def _passes_needed(longest: int, target: int, model_scale: int) -> int:
    """How many chained neural passes are required to reach the target."""
    if longest <= 0 or target <= longest:
        return 1
    passes = 1
    current = longest * model_scale
    while current < target and passes < MAX_CLI_PASSES:
        current *= model_scale
        passes += 1
    return passes


def _build_command(
    executable: str,
    source: Path,
    destination: Path,
    options: UpscaleOptions,
    model_dir: Path,
) -> list[str]:
    command = [
        executable,
        "-i", str(source),
        "-o", str(destination),
        "-m", str(model_dir),
        "-n", options.model,
        "-z", str(options.model_scale),
        "-g", str(options.gpu_id),
        "-c", str(options.compression),
        "-j", options.threads_arg,
        "-f", "png",  # lossless intermediate; the final encode is ours
        "-v",
    ]
    if options.tile_size != TILE_AUTO:
        command += ["-t", str(options.tile_size)]
    if options.tta:
        command.append("-x")
    return command


def _run_pass(
    command: list[str],
    timeout: int,
    on_progress: ProgressCallback | None,
    *,
    pass_index: int,
    pass_count: int,
) -> tuple[bool, str]:
    """Execute one CLI pass, streaming progress.

    Returns ``(completed, diagnostics)``. ``completed`` is False only when the
    process could not be started, timed out, or had to be killed. It is *not* a
    success signal: the binary exits 1 even when it succeeds, so the caller
    decides based on whether a decodable output file appeared.
    """
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        return False, f"Could not run the upscaler: {exc}"

    started = time.time()
    last_reported = -1.0
    error_lines: list[str] = []

    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue

            if time.time() - started > timeout:
                process.kill()
                return False, f"Upscaler timed out after {timeout}s."

            match = _PROGRESS_RE.search(line)
            if match:
                try:
                    percent = float(match.group(1))
                except ValueError:
                    continue
                # ncnn reports per tile, so the same value repeats many times and
                # can dip between passes. Only forward genuine forward movement:
                # every callback crosses a thread boundary into the job registry.
                if percent <= last_reported:
                    continue
                last_reported = percent
                if on_progress:
                    # Spread this pass's 0-100 across the whole run.
                    overall = ((pass_index + percent / 100.0) / pass_count) * 100.0
                    label = (
                        f"Upscaling · pass {pass_index + 1}/{pass_count} · "
                        f"{percent:.0f}%"
                    )
                    on_progress(overall, label)
                continue

            lowered = line.lower()
            if any(hint in lowered for hint in _ERROR_HINTS):
                error_lines.append(line)
    finally:
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
        if process.stdout is not None:
            process.stdout.close()

    # Deliberately NOT checking returncode: the binary exits 1 on success.
    # Collected diagnostics are returned rather than treated as failure, because
    # the CLI logs benign warnings this way; they only matter if no output file
    # appears, in which case they are the only useful explanation.
    return True, " ".join(error_lines[-3:])[:400]


def _target_dimensions(
    source_width: int,
    source_height: int,
    target_long_edge: int,
) -> tuple[int, int]:
    """Scale geometry so the long edge matches, preserving aspect ratio."""
    longest = max(source_width, source_height)
    if longest <= 0:
        return source_width, source_height
    factor = target_long_edge / longest
    return (
        max(1, int(round(source_width * factor))),
        max(1, int(round(source_height * factor))),
    )


def _resize_to(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize with the right kernel for the direction of travel."""
    current_height, current_width = image.shape[:2]
    if (current_width, current_height) == (width, height):
        return image

    shrinking = width < current_width or height < current_height
    # INTER_AREA is the correct choice when reducing (it averages, avoiding
    # aliasing); Lanczos is the best general upsampler.
    interpolation = cv2.INTER_AREA if shrinking else cv2.INTER_LANCZOS4
    return cv2.resize(image, (width, height), interpolation=interpolation)


def _megapixel_ceiling_long_edge(
    source_width: int,
    source_height: int,
    ceiling_megapixels: float,
) -> int:
    """Largest long edge that keeps the output under Adobe's MP ceiling."""
    if source_width <= 0 or source_height <= 0:
        return 0
    pixels = ceiling_megapixels * 1_000_000
    factor = (pixels / (source_width * source_height)) ** 0.5
    return int(max(source_width, source_height) * factor)


def upscale_image(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    options: UpscaleOptions | None = None,
    settings: Settings | None = None,
    on_progress: ProgressCallback | None = None,
    executable: str | None | object = _AUTO,
) -> UpscaleRunResult:
    """Upscale one image with the neural CLI, falling back to resampling.

    Args:
        file_path: Image to upscale (never modified).
        output_dir: Directory that receives the upscaled copy.
        record_id: Used to name the output file deterministically.
        options: Validated Stage 3 options; the configured defaults are used
            when omitted.
        settings: Application settings override.
        on_progress: Called with ``(percent, label)`` as the CLI reports progress.
        executable: Pre-resolved CLI path. Left unset the binary is probed for;
            passing ``None`` forces the resample fallback.

    Returns:
        An :class:`UpscaleRunResult` naming the backend that actually ran.
    """
    cfg = settings or default_settings
    started = time.time()
    source = Path(file_path)

    if not source.exists():
        return UpscaleRunResult(False, reason=f"File not found: {file_path}")

    image = _read_image(source)
    if image is None:
        return UpscaleRunResult(False, reason=f"Could not decode image: {file_path}")

    source_height, source_width = image.shape[:2]
    options = options or _default_options(cfg)

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / f"{record_id}-upscaled.jpg"

    # Clamp the target so a large capacity choice cannot breach Adobe's ceiling.
    ceiling = float(getattr(cfg, "ADOBE_MAX_MEGAPIXELS", 100.0))
    max_long_edge = _megapixel_ceiling_long_edge(source_width, source_height, ceiling)
    target_long_edge = options.target_long_edge
    warnings: list[str] = []
    if max_long_edge and target_long_edge > max_long_edge:
        warnings.append(
            f"Capacity reduced to {max_long_edge} px to stay under Adobe Stock's "
            f"{ceiling:.0f} MP ceiling."
        )
        target_long_edge = max_long_edge

    longest = max(source_width, source_height)
    already_large = longest >= target_long_edge
    if already_large and not options.allow_downscale:
        # Never discard resolution the contributor already has.
        target_long_edge = longest
        warnings.append(
            f"The source is already {longest} px on its long edge; it was kept at "
            "its native size."
        )

    target_width, target_height = _target_dimensions(
        source_width, source_height, target_long_edge
    )

    base = UpscaleRunResult(
        success=True,
        output_path=str(destination),
        source_dimensions=(source_width, source_height),
        output_dimensions=(target_width, target_height),
        scale=target_long_edge / longest if longest else 1.0,
        model=options.model,
        model_scale=options.model_scale,
        gpu_id=options.gpu_id,
        tta=options.tta,
        tile_size=options.tile_size,
        target_long_edge=target_long_edge,
        warnings=warnings,
    )

    # Nothing to upscale: re-encode (which embeds the sRGB profile) rather than
    # spending GPU time to produce a neural pass and then shrink it back down.
    needs_upscale = target_long_edge > longest

    resolved = find_cli(cfg) if executable is _AUTO else executable
    cli = resolved if needs_upscale else None
    if cli:
        neural = _run_neural(
            cli, source, output_root, record_id, image, options, cfg,
            target_width, target_height, on_progress,
        )
        if neural is not None:
            neural.warnings = warnings + neural.warnings
            neural.source_dimensions = (source_width, source_height)
            neural.duration_seconds = time.time() - started
            return neural

        warnings.append("The neural upscaler failed; fell back to resampling.")
        base.warnings = warnings

    # ---- resample fallback ------------------------------------------------- #
    if on_progress:
        on_progress(15.0, "Resampling…")

    resampled = _resize_to(image, target_width, target_height)
    resized = (target_width, target_height) != (source_width, source_height)
    if resized:
        # A restrained unsharp pass restores the acutance Lanczos leaves behind.
        blurred = cv2.GaussianBlur(resampled, (0, 0), 1.0)
        resampled = np.clip(
            cv2.addWeighted(resampled, 1.35, blurred, -0.35, 0), 0, 255
        ).astype(np.uint8)

    quality = int(getattr(cfg, "EXPORT_JPEG_QUALITY", 95))
    if on_progress:
        on_progress(80.0, "Encoding JPEG…")

    if options.embed_srgb:
        written = write_srgb_jpeg(resampled, destination, quality=quality)
    else:
        written = bool(
            cv2.imwrite(
                str(destination),
                resampled,
                [
                    cv2.IMWRITE_JPEG_QUALITY, quality,
                    cv2.IMWRITE_JPEG_CHROMA_QUALITY, 100,
                ],
            )
        )

    if not written:
        return UpscaleRunResult(
            False, reason="Failed to write the upscaled image.", warnings=warnings
        )

    if on_progress:
        on_progress(100.0, "Done")

    base.backend = BACKEND_RESAMPLE
    base.srgb_embedded = _srgb_was_written(destination, options)
    base.output_dimensions = _dimensions_of(destination)
    base.reason = (
        "Re-encoded at its native size; no upscale was required."
        if not resized
        else "Upscaled with high-quality Lanczos resampling. The neural upscaler "
        "was unavailable for this image."
    )
    base.duration_seconds = time.time() - started
    return base


def _default_options(cfg: Settings) -> UpscaleOptions:
    from services.upscale.options import default_options

    return default_options(cfg)


def _dimensions_of(path: Path) -> tuple[int, int]:
    image = _read_image(path)
    if image is None:
        return (0, 0)
    height, width = image.shape[:2]
    return (width, height)


def _srgb_was_written(destination: Path, options: UpscaleOptions) -> bool:
    """Report whether the file really carries an sRGB profile.

    Checking the written file rather than echoing ``options.embed_srgb`` matters:
    the profile build can fail, in which case the encoder degrades to an untagged
    JPEG. Reporting the request instead of the outcome would tell Adobe's
    requirements were met when they were not.
    """
    if not options.embed_srgb:
        return False
    return has_srgb_profile(destination)


def measure(file_path: str | Path) -> tuple[int, int] | None:
    """Read an image's ``(width, height)`` without decoding it twice.

    Used by the estimate endpoint, which needs the source geometry before it can
    predict what the configured capacity would produce.
    """
    path = Path(file_path)
    if not path.is_file():
        return None
    dimensions = _dimensions_of(path)
    return dimensions if dimensions != (0, 0) else None


def _run_neural(
    executable: str,
    source: Path,
    output_root: Path,
    record_id: str,
    source_image: np.ndarray,
    options: UpscaleOptions,
    cfg: Settings,
    target_width: int,
    target_height: int,
    on_progress: ProgressCallback | None,
) -> UpscaleRunResult | None:
    """Run the CLI (chaining passes if needed) and post-process the result.

    Returns None when the neural path could not produce a usable file, which
    signals the caller to fall back to resampling.
    """
    model = catalog.get_model(options.model, cfg)
    if model is None:
        logger.warning("Upscayl model '%s' is not installed", options.model)
        return None

    source_height, source_width = source_image.shape[:2]
    longest = max(source_width, source_height)
    pass_count = _passes_needed(longest, options.target_long_edge, options.model_scale)

    timeout = int(getattr(cfg, "UPSCAYL_TIMEOUT_SECONDS", 600))
    model_dir = Path(model.directory)

    # The neural render lands here; it is deleted once the final JPEG exists.
    intermediate = output_root / f"{record_id}-upscaled.cli.png"
    current_source = source
    last_detail = ""

    for index in range(pass_count):
        stage_output = (
            intermediate if index == pass_count - 1
            else output_root / f"{record_id}-upscaled.pass{index}.png"
        )

        command = _build_command(
            executable, current_source, stage_output, options, model_dir
        )
        ok, detail = _run_pass(
            command, timeout, on_progress,
            pass_index=index, pass_count=pass_count,
        )
        last_detail = detail or last_detail

        produced = stage_output.is_file() and _read_image(stage_output) is not None
        if not produced:
            _cleanup(stage_output, intermediate)
            logger.warning("Upscayl produced no usable output: %s", detail)
            return None

        # A chained pass consumes the previous pass's output.
        if index > 0:
            _cleanup(output_root / f"{record_id}-upscaled.pass{index - 1}.png")
        current_source = stage_output

    final_render = _read_image(intermediate)
    if final_render is None:
        _cleanup(intermediate)
        return None

    if on_progress:
        on_progress(92.0, "Resizing and embedding sRGB…")

    resized = _resize_to(final_render, target_width, target_height)
    quality = int(getattr(cfg, "EXPORT_JPEG_QUALITY", 95))
    destination = output_root / f"{record_id}-upscaled.jpg"

    if options.embed_srgb:
        written = write_srgb_jpeg(resized, destination, quality=quality)
    else:
        written = bool(
            cv2.imwrite(
                str(destination),
                resized,
                [
                    cv2.IMWRITE_JPEG_QUALITY, quality,
                    cv2.IMWRITE_JPEG_CHROMA_QUALITY, 100,
                ],
            )
        )

    _cleanup(intermediate)

    if not written:
        return UpscaleRunResult(
            False, backend=BACKEND_NEURAL, reason="Failed to write the upscaled image."
        )

    if on_progress:
        on_progress(100.0, "Done")

    pass_note = f" in {pass_count} passes" if pass_count > 1 else ""
    embedded = _srgb_was_written(destination, options)
    # The caller prepends its own warnings, so start a fresh list here.
    neural_warnings: list[str] = []
    if options.embed_srgb and not embedded:
        neural_warnings.append(
            "The sRGB ICC profile could not be embedded; the file is untagged."
        )
    return UpscaleRunResult(
        success=True,
        output_path=str(destination),
        backend=BACKEND_NEURAL,
        scale=target_width / source_width if source_width else 1.0,
        output_dimensions=_dimensions_of(destination),
        model=model.name,
        model_scale=options.model_scale,
        gpu_id=options.gpu_id,
        tta=options.tta,
        tile_size=options.tile_size,
        passes=pass_count,
        target_long_edge=options.target_long_edge,
        srgb_embedded=embedded,
        reason=(
            f"Upscaled with '{model.name}' on GPU {options.gpu_id}{pass_note}"
            + (" with TTA" if options.tta else "")
            + (
                "; sRGB profile embedded."
                if embedded
                else "; sRGB profile could NOT be embedded."
            )
        ),
        warnings=neural_warnings,
    )


def _cleanup(*paths: Path) -> None:
    """Remove intermediate render files, ignoring anything already gone."""
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            logger.debug("Could not remove intermediate file %s", path)
