"""Background removal facade for PNG batches (batch pipeline v2).

Two responsibilities, deliberately separated:

1. **Segmentation** — run a salient-object model through ``rembg`` on the
   **CUDA execution provider** (see :mod:`services.gpu_env`) with a small LRU
   of ONNX sessions, so the first call loads the model once and later calls
   reuse it without holding every model in VRAM.
2. **Stock hardening** — hand the raw mask to :mod:`services.matting`, which
   runs the sub-pixel refinement, colour decontamination and alpha sanitising a
   100%-crop Adobe inspection demands (see that package's docstring for the
   blueprint). The caller's step config picks the model and which stages run.

The importer is deferred: ``rembg`` pulls in onnxruntime, which is heavy, and
the rest of the app (raster batches, tests) must not pay for it or fail when it
is missing. Every public function degrades with a clear ``reason`` string rather
than an ImportError.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from config import Settings, settings as default_settings
from services import gpu_env

logger = logging.getLogger(__name__)

#: Models offered in the UI, best-first. BiRefNet is the SOTA choice for
#: fine-edge preservation (antennae, root hairs); BRIA RMBG is trained for
#: commercial cut-out quality; ISNet/U²Net remain for speed and comparison.
SUPPORTED_MODELS: tuple[str, ...] = (
    "birefnet-general",
    "birefnet-massive",
    "birefnet-general-lite",
    "bria-rmbg",
    "isnet-general-use",
    "u2net",
)
DEFAULT_MODEL = "birefnet-general"

#: How many ONNX sessions may be resident at once. Keep this at **1**.
#:
#: A BiRefNet-class model is ~1 GB of weights and onnxruntime keeps host
#: *and* device copies of the graph plus its arena, so two live sessions can
#: push several GB of RSS — this box also runs other projects, and an
#: unbounded cache was already observed dying with ``bad allocation``. One
#: batch uses one model, so a single slot loses nothing but the reload on a
#: model change, which happens at most once per batch.
MAX_SESSIONS = 1

#: ``model + providers`` -> loaded rembg session, oldest access first.
_sessions: OrderedDict[tuple[str, tuple[str, ...]], object] = OrderedDict()


def release_sessions() -> int:
    """Drop every cached ONNX session and return how many were freed.

    Called when a background-removal step finishes (success, failure or
    cancel) so a ~1 GB model is not left resident while the rest of the batch,
    or an unrelated job, is working.
    """
    freed = len(_sessions)
    _sessions.clear()
    if freed:
        logger.info("Released %d cached ONNX session(s).", freed)
    return freed


@dataclass
class RemoveResult:
    """Outcome of one background-removal attempt."""

    success: bool
    output_path: str | None = None
    model: str = ""
    width: int | None = None
    height: int | None = None
    reason: str = ""
    #: Per-stage report from :func:`services.matting.refine_cutout`.
    stages: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "model": self.model,
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
            "stages": self.stages,
        }


def _get_session(model: str, providers: list[str] | None = None):
    """Load (and cache) a rembg session for ``model`` on ``providers``.

    The cache key includes the providers: a CPU and a CUDA session of the same
    model are different objects, and silently handing back the wrong one is how
    "I asked for the GPU and got the CPU" bugs happen.
    """
    wanted = list(providers or gpu_env.execution_providers(True))
    # Provider *options* are dicts, so the cache key goes through
    # provider_cache_key() rather than tuple(wanted) — which would be
    # unhashable the moment the CUDA spec carries an option.
    key = (model, gpu_env.provider_cache_key(wanted))

    cached = _sessions.pop(key, None)
    if cached is not None:
        _sessions[key] = cached  # re-insert: OrderedDict pops oldest first
        return cached

    from rembg import new_session  # deferred: heavy import

    session = new_session(model, providers=wanted)
    _sessions[key] = session
    while len(_sessions) > MAX_SESSIONS:
        _sessions.popitem(last=False)
    logger.info(
        "Loaded rembg session %s on %s", model, gpu_env.active_providers(session)
    )
    return session


def _segment(
    source: Image.Image, model: str, providers: list[str]
) -> tuple[np.ndarray, object]:
    """Run the model; returns ``(HxWx4 uint8 RGBA, session)``."""
    from rembg import remove as _rembg_remove  # deferred: heavy import

    session = _get_session(model, providers)
    # ``convert`` keeps alpha when present; on an opaque input the cut is
    # simply a full-coverage alpha, which the edge check reports on.
    rgba = source.convert("RGBA")
    result = _rembg_remove(rgba, session=session)
    return np.asarray(result.convert("RGBA"), dtype=np.uint8), session


def remove_background(
    source_path: str | Path,
    record_id: str,
    *,
    model: str = DEFAULT_MODEL,
    cfg: Settings | None = None,
    options: dict | None = None,
) -> RemoveResult:
    """Cut the object out of ``source_path``; write a hardened RGBA PNG.

    ``options`` is the ``bg_remove`` step config (``gpu``, ``matting``,
    ``defringe``, ``sanitize`` and friends). It is merged over
    :data:`services.matting.DEFAULT_CONFIG`, so a profile saved before those
    keys existed still runs.

    Returns a :class:`RemoveResult` — never raises for a per-image failure, so
    one broken file cannot abort the batch (the runner reports it instead).
    """
    settings = cfg or default_settings
    source = Path(source_path)
    if not source.exists():
        return RemoveResult(success=False, model=model, reason=f"Source not found: {source}")

    chosen = model if model in SUPPORTED_MODELS else DEFAULT_MODEL
    opts = dict(options or {})
    want_gpu = bool(opts.get("gpu", True))
    providers = gpu_env.execution_providers(want_gpu)
    if want_gpu and not gpu_env.cuda_usable():
        # Say so once, in the log and on the record — a silent CPU fallback is
        # indistinguishable from "the GPU is working" until someone times it.
        logger.warning("GPU requested but CUDAExecutionProvider is unavailable; using CPU.")

    try:
        from services.matting import refine_cutout

        with Image.open(source) as img:
            raw, session = _segment(img, chosen, providers)

        hardened, stages = refine_cutout(raw, options)
        stages["device"] = {
            "requested": "gpu" if want_gpu else "cpu",
            "providers": gpu_env.active_providers(session),
            "cuda_usable": gpu_env.cuda_usable(),
            # Which cuDNN conv-algo search was asked for; visible in the UI so
            # a FALLBACK-vs-EXHAUSTIVE experiment needs no log diving.
            "conv_algo": gpu_env.conv_algo() if want_gpu else "cpu",
        }

        out_dir = Path(settings.REMOVED_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{record_id}.png"
        Image.fromarray(hardened, "RGBA").save(out_path, "PNG")
        return RemoveResult(
            success=True,
            output_path=str(out_path),
            model=chosen,
            width=hardened.shape[1],
            height=hardened.shape[0],
            stages=stages,
        )
    except ImportError as exc:
        return RemoveResult(
            success=False,
            model=chosen,
            reason=(
                "Background removal is unavailable: the 'rembg' package is not installed."
                if "rembg" in str(exc)
                else f"Background removal dependency missing: {exc}"
            ),
        )
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
        logger.exception("Background removal failed for %s", source)
        return RemoveResult(success=False, model=chosen, reason=f"Removal error: {exc}")


__all__ = [
    "DEFAULT_MODEL",
    "MAX_SESSIONS",
    "RemoveResult",
    "SUPPORTED_MODELS",
    "release_sessions",
    "remove_background",
]
