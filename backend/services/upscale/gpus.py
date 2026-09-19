"""Vulkan device enumeration for the bundled Upscayl CLI.

The upscaler takes a device index (``-g``), so the UI has to offer exactly the
indices this machine's Vulkan runtime exposes. A hard-coded list is wrong on
every machine but the one it was written on: a laptop with only an integrated
GPU would be offered a discrete device that does not exist, and a workstation
with two discrete GPUs would silently never use the second one.

The CLI has no "list devices" flag, but it prints a per-device capability banner
as soon as it starts, before it validates anything else. Probing with
deliberately invalid arguments therefore enumerates the devices and exits in
well under a second:

    [0 NVIDIA GeForce GTX 1660 Ti]  queueC=2[8]  queueG=0[16]  queueT=1[2]
    [0 NVIDIA GeForce GTX 1660 Ti]  fp16-p/s/a=1/1/1  int8-p/s/a=1/1/1
    [1 Intel(R) UHD Graphics]       queueC=0[1]  queueG=0[1]  queueT=0[1]

Only the first line per index is kept; the rest is per-device detail. The
reported index is used verbatim as the device id, because re-ordering here would
make the UI select a different device than the one it names.

Device *kind* is a presentation concern, so it is inferred from the adapter name
and only ever used for labelling and for choosing a default - never to renumber.
"""

from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field

from config import Settings, settings as default_settings
from services.upscale.catalog import model_directories
from services.upscale.runner import find_cli

logger = logging.getLogger(__name__)

#: Device kinds reported to the UI.
KIND_DEDICATED = "dedicated"
KIND_INTEGRATED = "integrated"
KIND_SOFTWARE = "software"
KIND_UNKNOWN = "unknown"

#: Matches the CLI's device banner, e.g. ``[0 NVIDIA GeForce GTX 1660 Ti]``.
#: The trailing ``]`` must be followed by whitespace so that a bracketed word
#: inside a model name can never be mistaken for a device.
_DEVICE_RE = re.compile(r"^\s*\[(\d+)\s+([^\]]+?)\]\s", re.MULTILINE)

#: Trademark noise in adapter names, stripped before classification so that
#: ``Intel(R) Arc(TM) A770`` matches the same hints as ``Intel Arc A770``.
_NOISE_RE = re.compile(r"\s*[\u00ae\u2122]|\s*\((?:r|tm|c)\)", re.IGNORECASE)

#: How long a probe result is reused. Enumeration costs a process spawn, and the
#: device list cannot change without a driver reinstall, so this is generous.
_CACHE_TTL_SECONDS = 300.0

#: Adapter-name fragments that identify a software rasterizer. These are
#: reported by the driver and are always the slowest option available.
_SOFTWARE_HINTS = (
    "llvmpipe",
    "swiftshader",
    "software rasterizer",
    "basic render driver",
)

#: Adapter-name fragments that identify an integrated GPU.
_INTEGRATED_HINTS = (
    "intel",
    "uhd graphics",
    "hd graphics",
    "iris",
    "vega",
    "radeon graphics",
    "apple m",
)

#: Adapter-name fragments that identify a discrete GPU. Checked before the
#: integrated list, because "Radeon RX" and "Radeon Graphics" differ only in the
#: suffix and both contain "radeon".
_DEDICATED_HINTS = (
    "geforce",
    "nvidia",
    "quadro",
    "tesla",
    "rtx",
    "gtx",
    "radeon rx",
    "radeon pro",
    "arc a",
    "arc b",
    "arc pro",
)

#: Arguments used purely to make the CLI print its device banner and stop.
#:
#: Two constraints were discovered by probing the real binary:
#:
#: * The input path must be *non-empty* - given ``-i ""`` the CLI prints its
#:   usage text and exits before it initialises Vulkan, so no banner appears.
#: * The model directory must look like a model directory - it validates ``-m``
#:   (and rejects a folder not named ``models``) *before* enumerating devices.
#:   A real installed model folder is therefore passed in, which also keeps the
#:   probe honest about what the operator can actually run.
_PROBE_ARGS = (
    "-i",
    "__enumerate__.jpg",
    "-o",
    "__enumerate__.png",
    "-n",
    "__enumerate__",
    "-z",
    "2",
    "-g",
    "-1",
    "-f",
    "png",
    "-v",
)

#: The probe is expected to fail. This cap only guards against a hung driver.
_PROBE_TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class GpuDevice:
    """One Vulkan device the CLI can be pointed at with ``-g``."""

    id: int
    name: str
    kind: str
    #: True for the device the pipeline should default to.
    recommended: bool = False
    #: Extra per-device detail from the banner, when it was parsed.
    details: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Short human label, e.g. ``NVIDIA GeForce GTX 1660 Ti``."""
        return self.name

    @property
    def kind_label(self) -> str:
        """Title-cased kind, matching the wording used in the UI."""
        return self.kind.capitalize()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "recommended": self.recommended,
            "details": dict(self.details),
        }


def classify(name: str) -> str:
    """Best-effort device kind from its adapter name.

    The driver is the only source of truth and it does not report this, so the
    result is a hint used for labelling and default selection.
    """
    lowered = _NOISE_RE.sub("", name).lower()

    for hint in _SOFTWARE_HINTS:
        if hint in lowered:
            return KIND_SOFTWARE
    for hint in _DEDICATED_HINTS:
        if hint in lowered:
            return KIND_DEDICATED
    for hint in _INTEGRATED_HINTS:
        if hint in lowered:
            return KIND_INTEGRATED
    return KIND_UNKNOWN


def _parse_devices(output: str) -> list[GpuDevice]:
    """Extract one :class:`GpuDevice` per index from the CLI banner."""
    seen: dict[int, str] = {}
    for raw_index, raw_name in _DEVICE_RE.findall(output):
        index = int(raw_index)
        name = raw_name.strip()
        # The banner repeats the index for each capability line; the first
        # occurrence carries the adapter name.
        if index not in seen and name:
            seen[index] = name

    devices = [
        GpuDevice(id=index, name=name, kind=classify(name))
        for index, name in sorted(seen.items())
    ]
    return _mark_recommended(devices)


def _mark_recommended(devices: list[GpuDevice]) -> list[GpuDevice]:
    """Flag the device the pipeline should default to.

    Preference order is discrete > unknown > integrated > software. Ties keep the
    lowest index, which is the order the driver reported and therefore the order
    the CLI itself would pick.
    """
    rank = {
        KIND_DEDICATED: 0,
        KIND_UNKNOWN: 1,
        KIND_INTEGRATED: 2,
        KIND_SOFTWARE: 3,
    }
    if not devices:
        return devices

    best = min(devices, key=lambda device: (rank.get(device.kind, 1), device.id))
    return [
        GpuDevice(
            id=device.id,
            name=device.name,
            kind=device.kind,
            recommended=device.id == best.id,
            details=device.details,
        )
        for device in devices
    ]


def _probe(cli: str, settings: Settings | None = None) -> str:
    """Run the CLI once and return everything it printed.

    A non-zero exit is the expected outcome and is not an error: the banner is
    printed during Vulkan initialisation, before the arguments are validated.
    """
    cfg = settings or default_settings
    command = [cli, *_PROBE_ARGS]

    model_dir = _probe_model_dir(cfg)
    if model_dir:
        command += ["-m", model_dir]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("GPU enumeration timed out after %.0fs", _PROBE_TIMEOUT_SECONDS)
        return ""
    except OSError:
        logger.exception("Could not launch %s for GPU enumeration", cli)
        return ""

    return f"{completed.stdout or ''}\n{completed.stderr or ''}"


def _probe_model_dir(cfg: Settings) -> str | None:
    """A real model folder to pass as ``-m``, or None when none is installed."""
    for _, directory in model_directories(cfg):
        if directory.is_dir():
            return str(directory)
    return None


#: Cached device list plus the monotonic timestamp it was captured at.
_cache: tuple[float, list[GpuDevice]] | None = None


def clear_cache() -> None:
    """Drop the cached enumeration, forcing the next call to re-probe."""
    global _cache
    _cache = None


def list_gpus(
    settings: Settings | None = None,
    *,
    refresh: bool = False,
) -> list[GpuDevice]:
    """Every Vulkan device the upscaler can be pointed at.

    Returns an empty list when no CLI is installed or the probe yields nothing,
    which lets callers fall back to a sensible default rather than showing a
    device picker that cannot work.
    """
    global _cache

    cfg = settings or default_settings
    cli = find_cli(cfg)
    if not cli:
        return []

    now = time.monotonic()
    if not refresh and _cache is not None:
        captured_at, devices = _cache
        if now - captured_at < _CACHE_TTL_SECONDS:
            return devices

    devices = _parse_devices(_probe(cli, cfg))
    _cache = (now, devices)
    return devices


def default_gpu_id(settings: Settings | None = None) -> int:
    """The device index the pipeline should use when none is chosen.

    Mirrors the CLI's own ``auto`` behaviour closely enough to be predictable:
    the recommended device, or device 0, or 0 when nothing was enumerated.
    """
    devices = list_gpus(settings)
    for device in devices:
        if device.recommended:
            return device.id
    return devices[0].id if devices else 0


def gpus_payload(
    settings: Settings | None = None,
    *,
    refresh: bool = False,
) -> dict:
    """Device list plus the default, ready for the Stage 3 options panel."""
    devices = list_gpus(settings, refresh=refresh)
    default_id = next(
        (device.id for device in devices if device.recommended),
        devices[0].id if devices else 0,
    )
    return {
        "devices": [device.to_dict() for device in devices],
        "default_gpu_id": default_id,
        "available": bool(devices),
    }
