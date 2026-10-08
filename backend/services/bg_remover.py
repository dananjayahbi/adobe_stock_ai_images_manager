"""Background removal facade for PNG batches (batch pipeline v2).

Uses ``rembg`` under the hood with an isolated ONNX session per model name, so
the first call downloads/loads the model once and later calls reuse it. The
output is an RGBA PNG written to ``storage/removed/{record_id}.png``.

The importer is deferred: ``rembg`` pulls in onnxruntime, which is heavy, and
the rest of the app (raster batches, tests) must not pay for it or fail when it
is missing. Every public function degrades with a clear ``reason`` string rather
than an ImportError.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import Settings, settings as default_settings

logger = logging.getLogger(__name__)

#: Models offered in the UI. ``isnet-general-use`` is the strong default.
SUPPORTED_MODELS: tuple[str, ...] = ("isnet-general-use", "u2net", "birefnet-general")
DEFAULT_MODEL = "isnet-general-use"

_sessions: dict[str, object] = {}


@dataclass
class RemoveResult:
    """Outcome of one background-removal attempt."""

    success: bool
    output_path: str | None = None
    model: str = ""
    width: int | None = None
    height: int | None = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "model": self.model,
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
        }


def _get_session(model: str):
    """Load (and cache) a rembg session for ``model``."""
    if model in _sessions:
        return _sessions[model]
    from rembg import new_session  # deferred: heavy import

    session = new_session(model)
    _sessions[model] = session
    return session


def remove_background(
    source_path: str | Path,
    record_id: str,
    *,
    model: str = DEFAULT_MODEL,
    cfg: Settings | None = None,
) -> RemoveResult:
    """Cut the object out of ``source_path``; write an RGBA PNG.

    Returns a :class:`RemoveResult` — never raises for a per-image failure, so
    one broken file cannot abort the batch (the runner reports it instead).
    """
    settings = cfg or default_settings
    source = Path(source_path)
    if not source.exists():
        return RemoveResult(success=False, model=model, reason=f"Source not found: {source}")

    chosen = model if model in SUPPORTED_MODELS else DEFAULT_MODEL
    try:
        from rembg import remove as _rembg_remove  # deferred: heavy import

        session = _get_session(chosen)
        with Image.open(source) as img:
            # ``convert`` keeps alpha when present; on an opaque input the cut
            # is simply a full-coverage alpha, which the edge check reports on.
            rgba = img.convert("RGBA")
            result: Image.Image = _rembg_remove(rgba, session=session)

        out_dir = Path(settings.REMOVED_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{record_id}.png"
        result.save(out_path, "PNG")
        return RemoveResult(
            success=True,
            output_path=str(out_path),
            model=chosen,
            width=result.width,
            height=result.height,
        )
    except ImportError:
        return RemoveResult(
            success=False,
            model=chosen,
            reason="Background removal is unavailable: the 'rembg' package is not installed.",
        )
    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
        logger.exception("Background removal failed for %s", source)
        return RemoveResult(success=False, model=chosen, reason=f"Removal error: {exc}")
