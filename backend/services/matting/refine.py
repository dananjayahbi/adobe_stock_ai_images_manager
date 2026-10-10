"""Stage 3 of the stock-grade cut-out: sub-pixel alpha refinement.

Takes the coarse probability mask a SOD model produced and recomputes only the
*transition band*, where a binary mask and the truth disagree: inside the band
the alpha comes from an edge-aware refiner, definite foreground keeps its
value, and definite background is snapped to 0 (the coarse model's weak tail
there is noise, not signal).

Two refiners:

* ``guided``  — the guided filter in :mod:`.guided`. Always available, no
  model, no network. This is the default.
* ``vitmatte`` — ViTMatte via ``transformers`` when it is installed. A neural
  matte that solves the unknown band properly (sub-pixel transparency on hairs
  and antennae). Opt-in: the dependency and its weights are installed from the
  Config page (``/settings``) and stored under ``<repo>/models``, so this
  refiner runs offline once installed. Any failure degrades to ``guided`` with
  the reason recorded in the returned note.
"""

from __future__ import annotations

import logging

import numpy as np

from services import model_paths

from .guided import DEFAULT_EPS, DEFAULT_RADIUS, guided_filter, luma
from .trimap import DEFAULT_RADIUS as DEFAULT_TRIMAP_RADIUS
from .trimap import FOREGROUND, unknown_fraction, build_trimap

logger = logging.getLogger(__name__)

#: Model weights used when ``method="vitmatte"``.
VITMATTE_MODEL_ID = "hustvl/vitmatte-small-composition-1k"

#: Folder the Config-page installer snapshots the weights into (inside
#: ``<repo>/models``), so every weight this app uses stays in one copyable tree.
VITMATTE_LOCAL_DIRNAME = "huggingface-vitmatte"


def vitmatte_source() -> str:
    """Where ``from_pretrained`` should load ViTMatte from.

    The installer downloads the snapshot to
    ``<repo>/models/huggingface-vitmatte``. A bare repo id would send
    ``from_pretrained`` to the Hugging Face cache instead — and, on a metered
    connection, re-download the ~103 MB already sitting on disk. The local
    copy wins when it actually holds weights; otherwise the repo id is used
    and the cache takes over.
    """
    local = model_paths.MODELS_DIR / VITMATTE_LOCAL_DIRNAME
    if any(local.glob("*.safetensors")):
        return str(local)
    return VITMATTE_MODEL_ID

#: Every refiner is keyed here; unknown methods fall back to ``guided``.
METHODS = ("guided", "vitmatte", "off")

#: Width (in 0-1 alpha units) of the ramp left after refinement. The guided
#: filter buys positional accuracy by smoothing over its window, which also
#: widens the transition band — a milky edge is exactly what a 100% crop
#: rejects. Re-centring the ramp on the refined 0.5 crossing keeps the
#: *position* the refiner found while giving a hard subject a hard edge. ``0``
#: keeps the refiner's native softness (for genuinely translucent subjects).
DEFAULT_RAMP = 0.25


class MattingUnavailable(RuntimeError):
    """Raised when an optional refiner cannot run — callers fall back."""


def tighten_ramp(alpha01: np.ndarray, ramp: float, center: float = 0.5) -> np.ndarray:
    """Steepen a soft alpha around ``center`` without moving the crossing.

    0 maps to 0 and 1 maps to 1, so solid foreground and background are
    untouched; only values inside ``center ± ramp/2`` are reshaped.
    """
    width = float(ramp)
    if width <= 0.0 or width >= 1.0:
        return alpha01
    low = center - width / 2.0
    t = np.clip((alpha01 - low) / width, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _guided_alpha(rgb: np.ndarray, trimap: np.ndarray) -> np.ndarray:
    """Refine the band with the guided filter; returns alpha in 0-1."""
    radius = DEFAULT_RADIUS
    guide = luma(rgb)
    source = trimap.astype(np.float64) / 255.0
    return guided_filter(guide, source, radius=radius, eps=DEFAULT_EPS)


def _vitmatte_alpha(rgb: np.ndarray, trimap: np.ndarray) -> np.ndarray:
    """Refine the band with ViTMatte. Raises :class:`MattingUnavailable`."""
    try:
        import torch
        from transformers import VitMatteForImageMatting
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise MattingUnavailable(f"transformers/torch not installed ({exc})") from exc

    # transformers >= 5 ships two processor backends for ViTMatte: the default
    # one is torchvision-backed, and torchvision is *not* a dependency of this
    # project (it would double the download and drag in its own CUDA wheels).
    # The PIL/numpy backend is a drop-in, so prefer it and only fall back to
    # the torchvision class for older transformers that predate it.
    try:
        from transformers import VitMatteImageProcessorPil as Processor
    except ImportError:
        from transformers import VitMatteImageProcessor as Processor

    try:
        from PIL import Image

        image = Image.fromarray(np.ascontiguousarray(rgb), "RGB")
        hint = Image.fromarray(np.ascontiguousarray(trimap), "L")
        source = vitmatte_source()
        processor = Processor.from_pretrained(source)
        model = VitMatteForImageMatting.from_pretrained(source)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = model.to(device).eval()

        inputs = processor(images=image, trimaps=hint, return_tensors="pt")
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            alphas = model(**inputs).alphas
        pred = alphas.squeeze().detach().cpu().numpy()
    except Exception as exc:  # noqa: BLE001 - any model failure must degrade
        raise MattingUnavailable(f"ViTMatte failed ({exc})") from exc

    height, width = trimap.shape
    # The processor pads to a multiple of the patch size; crop back so the
    # alpha always lands on the source pixel grid (no resize, no blur).
    pred = np.clip(pred[:height, :width], 0.0, 1.0)
    if pred.shape != trimap.shape:  # pragma: no cover - defensive
        raise MattingUnavailable(f"ViTMatte returned {pred.shape}, want {trimap.shape}")
    return pred.astype(np.float64)


_REFINERS = {
    "guided": _guided_alpha,
    "vitmatte": _vitmatte_alpha,
}


def refine_alpha(
    rgb: np.ndarray,
    alpha: np.ndarray,
    *,
    method: str = "guided",
    trimap_radius: int = DEFAULT_TRIMAP_RADIUS,
    ramp: float = DEFAULT_RAMP,
) -> tuple[np.ndarray, str]:
    """Recompute the transition band of ``alpha``; returns (alpha 0-255, note).

    ``rgb`` is HxWx3 (used only as an edge guide), ``alpha`` is HxW float.
    """
    base = np.asarray(alpha, dtype=np.float64)
    if base.ndim != 2:
        raise ValueError("refine_alpha expects an HxW alpha channel")

    chosen = method if method in _REFINERS else "guided"
    if method == "off":
        return base, "off"

    trimap = build_trimap(base, radius=trimap_radius)
    if unknown_fraction(trimap) == 0.0:
        return base, "trimap fully determined — nothing to refine"

    note = chosen
    try:
        refined = _REFINERS[chosen](rgb, trimap)
    except MattingUnavailable as exc:
        logger.warning("Matting refiner %r unavailable: %s — using guided", chosen, exc)
        refined = _guided_alpha(rgb, trimap)
        note = f"guided (fallback: {exc})"

    out = base.copy()
    # Definite background is definitely background — the coarse mask's weak
    # low-probability tail there is noise, not signal.
    out[trimap == 0] = 0.0
    band = trimap == 128
    band_alpha = np.clip(refined[band], 0.0, 1.0)
    out[band] = tighten_ramp(band_alpha, ramp) * 255.0
    return out, note


__all__ = [
    "DEFAULT_RAMP",
    "METHODS",
    "MattingUnavailable",
    "VITMATTE_MODEL_ID",
    "refine_alpha",
    "tighten_ramp",
    "FOREGROUND",
]
