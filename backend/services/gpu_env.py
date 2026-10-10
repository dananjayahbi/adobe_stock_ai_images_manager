"""Locate the CUDA/cuDNN DLLs ``onnxruntime-gpu`` needs, at the right moment.

``onnxruntime-gpu`` ships no CUDA: it resolves ``cudart`` / ``cublas`` /
``cudnn`` through the ordinary Windows DLL search *when a session is created*,
not at import time. Two facts about a normal dev box combine to break that:

* the NVIDIA pip wheels (``nvidia-cudnn-cu12``, ``nvidia-cublas-cu12``) drop
  their DLLs under ``site-packages/nvidia/<pkg>/bin``, which is never on PATH;
* a CUDA toolkit install *is* on PATH but ships an older cuDNN (8.x), which
  shadows the 9.x the runtime actually wants.

So: prepend every NVIDIA *wheel* bin directory ahead of the existing PATH, and
also register the directories with :func:`os.add_dll_directory`. Idempotent —
call it as often as you like, before the first session is built.
"""

from __future__ import annotations

import glob
import os
import sysconfig
from pathlib import Path

#: Providers worth requesting on a CUDA machine. Deliberately *not*
#: ``TensorrtExecutionProvider``: the wheel advertises it without shipping
#: TensorRT, so asking for it makes every session creation fail.
CUDA_PROVIDERS: tuple[str, ...] = ("CUDAExecutionProvider", "CPUExecutionProvider")
CPU_PROVIDERS: tuple[str, ...] = ("CPUExecutionProvider",)

#: ORT default is ``EXHAUSTIVE`` (cuDNN heuristic mode B). On this Turing GPU
#: with cuDNN 9.27 that mode finds *zero* engine configs for a plain FP32 conv
#: (``CUDNN_FE failure 8: HEURISTIC_QUERY_FAILED``) and the node falls back to
#: CPU. ``DEFAULT`` maps to cuDNN heuristic mode **FALLBACK** in
#: ``onnxruntime/core/providers/cuda/nn/conv.cc`` — the mode that runs when the
#: heuristics database has nothing for this architecture.
#:
#: Override without touching code: ``ORT_CUDNN_CONV_ALGO=EXHAUSTIVE`` (or
#: ``HEURISTIC``) before starting the backend.
CONV_ALGO_ENV = "ORT_CUDNN_CONV_ALGO"
VALID_CONV_ALGOS = ("EXHAUSTIVE", "HEURISTIC", "DEFAULT")

_dirs: list[str] = []
_applied = False


def conv_algo(override: str | None = None) -> str:
    """The ``cudnn_conv_algo_search`` value to request, upper-cased."""
    raw = override if override is not None else os.environ.get(CONV_ALGO_ENV, "DEFAULT")
    algo = str(raw).strip().upper() or "DEFAULT"
    return algo if algo in VALID_CONV_ALGOS else "DEFAULT"


def nvidia_dll_dirs() -> list[Path]:
    """Every ``nvidia/<package>/{bin,lib}`` directory holding a wheel DLL."""
    purelib = Path(os.fspath(sysconfig.get_paths()["purelib"]))
    found: list[Path] = []
    for pattern in ("nvidia/*/bin/*.dll", "nvidia/*/lib/*.dll"):
        for dll in sorted(glob.glob(str(purelib / pattern))):
            parent = Path(dll).parent
            if parent not in found:
                found.append(parent)
    return found


def ensure_cuda_dlls() -> list[str]:
    """Put the wheel DLL dirs first on PATH; return them (idempotent)."""
    global _applied, _dirs
    if _applied:
        return list(_dirs)

    _dirs = [os.fspath(p) for p in nvidia_dll_dirs()]
    if _dirs:
        wanted = {os.path.normcase(os.path.normpath(d)) for d in _dirs}
        # Drop any duplicate entries so the wheel's cuDNN 9 wins over the
        # toolkit's cuDNN 8 instead of racing with it.
        existing = [
            p
            for p in os.environ.get("PATH", "").split(os.pathsep)
            if p and os.path.normcase(os.path.normpath(p)) not in wanted
        ]
        os.environ["PATH"] = os.pathsep.join([*_dirs, *existing])
        if hasattr(os, "add_dll_directory"):
            for d in _dirs:
                try:
                    os.add_dll_directory(d)
                except OSError:  # pragma: no cover - already registered
                    pass
    _applied = True
    return list(_dirs)


def cuda_usable() -> bool:
    """True when this interpreter's onnxruntime actually exposes CUDA.

    Reads the *runtime* state, not a config flag, so "Use GPU" can honestly
    fall back to CPU on a machine whose onnxruntime build or driver is wrong.
    """
    ensure_cuda_dlls()
    try:
        import onnxruntime as ort
    except ImportError:  # pragma: no cover - dependency is required anyway
        return False
    return ort.get_device() == "GPU" and "CUDAExecutionProvider" in ort.get_available_providers()


def cuda_providers(algo: str | None = None) -> list:
    """CUDA + CPU as ORT's ``(name, options)`` provider specs.

    The option dict travels straight through ``rembg``: its ``BaseSession``
    only requires ``providers`` to be a list, and ORT accepts either plain
    names or ``(name, options)`` pairs — so the conv-algo search reaches the
    CUDA EP without patching the third-party package.
    """
    return [
        ("CUDAExecutionProvider", {"cudnn_conv_algo_search": conv_algo(algo)}),
        "CPUExecutionProvider",
    ]


def provider_cache_key(providers: list) -> tuple[str, ...]:
    """A hashable identity for a provider list (options are dicts)."""
    parts: list[str] = []
    for entry in providers:
        if isinstance(entry, tuple):
            name, options = entry
            opts = ",".join(f"{k}={v}" for k, v in sorted(dict(options).items()))
            parts.append(f"{name}({opts})")
        else:
            parts.append(str(entry))
    return tuple(parts)


def execution_providers(gpu: bool = True) -> list:
    """The provider list to hand to onnxruntime for this request."""
    if gpu and cuda_usable():
        return cuda_providers()
    return list(CPU_PROVIDERS)


def active_providers(session) -> list[str]:
    """Providers a live onnxruntime session ended up on (for reporting)."""
    inner = getattr(session, "inner_session", session)
    try:
        return list(inner.get_providers())
    except Exception:  # noqa: BLE001 - diagnostics only
        return []


__all__ = [
    "CONV_ALGO_ENV",
    "CPU_PROVIDERS",
    "CUDA_PROVIDERS",
    "VALID_CONV_ALGOS",
    "active_providers",
    "cuda_providers",
    "cuda_usable",
    "conv_algo",
    "ensure_cuda_dlls",
    "execution_providers",
    "nvidia_dll_dirs",
    "provider_cache_key",
]
