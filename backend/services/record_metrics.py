"""Record metrics - measurements of the file that will actually be **delivered**.

The bug this module exists to prevent
------------------------------------
`width`, `height`, `megapixels` and `file_size_bytes` were written exactly once,
at ingestion, measured on the **inbox original** - and never refreshed. But the
file the operator receives is the *working copy*: the PNG->JPEG conversion, the
refined pass, or the upscale.

So after a Stage 3 upscale the two disagreed by 8x. A published asset whose
delivered file is **3840x2143 (8.2 MP)** reported **1376x768 (1.06 MP)**, which
the gallery rendered under the image. To the operator that is indistinguishable
from "publishing shrank my image" - and it was reported to us as exactly that.

Worse, the number was not merely cosmetic: `low_resolution` is a **critical**
acceptance issue scored from the megapixels, so a stale 1.06 MP claimed a
below-Adobe-floor resolution for an asset that comfortably passes.

Why one shared function
-----------------------
Four call sites change `working_path` (upload conversion, upscale, refine,
autofix). Each one re-deriving the measurement is how the two drifted apart in
the first place, so all of them call :func:`refresh_delivery_metrics` instead.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image

from config import settings
from services.storage import resolve_ready_path

logger = logging.getLogger(__name__)


def delivered_path(record, cfg=None) -> Path | None:
    """The file this record will actually hand to the operator.

    Preference order mirrors the delivery layer exactly, because the measurement
    has to describe the same file the CSV names and the ZIP contains:

    1. the **staged** copy in ``ready_to_upload`` (once published),
    2. ``working_path`` - the pipeline's best copy,
    3. the inbox original, only when nothing better exists.

    Returns None when none of them is readable.
    """
    config = cfg or settings

    staged = resolve_ready_path(record, getattr(config, "READY_DIR", None))
    if staged is not None:
        return staged

    for candidate in (
        getattr(record, "working_path", None),
        getattr(record, "original_path", None),
    ):
        if candidate and Path(candidate).is_file():
            return Path(candidate)

    return None


def measure_image(path: Path | str) -> dict | None:
    """Read a file's real geometry and size, or None when it cannot be read."""
    candidate = Path(path)
    if not candidate.is_file():
        return None
    try:
        with Image.open(candidate) as image:
            width, height = image.size
    except Exception:  # noqa: BLE001 - a corrupt file must not break the pipeline
        logger.warning("Could not measure %s", candidate, exc_info=True)
        return None

    return {
        "width": width,
        "height": height,
        "megapixels": round((width * height) / 1_000_000, 4),
        "file_size_bytes": candidate.stat().st_size,
        "measured_path": str(candidate),
    }


def refresh_delivery_metrics(record, cfg=None) -> dict | None:
    """Re-measure a record against its deliverable file and update the columns.

    Called wherever ``working_path`` changes, so the reported geometry follows
    the pipeline instead of describing the raw upload forever.

    Deliberately **does not commit** - the caller owns the transaction, and every
    existing call site is already inside one. A failure to measure leaves the
    previous values untouched rather than zeroing them, because a wrong number is
    worse than a stale one that was at least once true.

    Returns the measurements applied, or None when nothing could be measured.
    """
    path = delivered_path(record, cfg)
    if path is None:
        return None

    measured = measure_image(path)
    if measured is None:
        return None

    record.width = measured["width"]
    record.height = measured["height"]
    record.megapixels = measured["megapixels"]
    record.file_size_bytes = measured["file_size_bytes"]

    # Record which file these numbers describe. Without it, a later reader cannot
    # tell a measurement of the deliverable from a measurement of the original -
    # which is precisely the ambiguity that caused this bug.
    details = dict(getattr(record, "stage_details", None) or {})
    details["metrics"] = dict(measured)
    record.stage_details = details

    return measured
