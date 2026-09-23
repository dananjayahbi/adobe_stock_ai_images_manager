"""Startup repair of delivery metrics recorded from the wrong file.

Records created before :mod:`services.record_metrics` existed carry the **inbox
original's** geometry and byte size while their deliverable is the working copy.
Measured on the operator's own data: a published asset whose delivered file is
3840x2143 (8.2 MP) reported 1376x768 (1.06 MP), and the same file reported as
0.9 MB when the staged copy was 3.4 MB.

Left alone, those numbers are not merely cosmetic - `low_resolution` is a
**critical** acceptance issue derived from the megapixels, so a stale 1.06 MP
claims a below-Adobe-floor resolution for an asset that comfortably passes.

This runs at startup and is *self-limiting*: a record is only repaired when the
recorded geometry disagrees with the file it actually delivers, so once a record
has been measured correctly it is skipped forever and startup stays cheap.
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from models import ImageRecord
from services import record_metrics

logger = logging.getLogger(__name__)

#: Only these stages can have a working copy or a staged file that differs from
#: the original. A COLLECTED record's deliverable *is* its original, so its
#: recorded metrics are already correct and there is nothing to check.
_STAGES_WITH_A_DELIVERABLE_COPY = (
    "OCR_CLEAR",
    "UPSCALED",
    "REFINED",
    "COMPATIBLE",
    "INCOMPATIBLE",
    "METADATA_READY",
    "PUBLISHED",
)


def repair_delivery_metrics(session_factory) -> int:
    """Re-measure records whose reported geometry does not match their deliverable.

    Args:
        session_factory: Callable returning a new Session.

    Returns:
        The number of records repaired. Zero on the second and every later start,
        which is what makes this safe to run on every boot.
    """
    db: Session = session_factory()
    repaired = 0
    try:
        candidates = (
            db.query(ImageRecord)
            .filter(ImageRecord.stage.in_(_STAGES_WITH_A_DELIVERABLE_COPY))
            .all()
        )

        for record in candidates:
            path = record_metrics.delivered_path(record)
            if path is None:
                continue
            measured = record_metrics.measure_image(path)
            if measured is None:
                continue

            # The recorded numbers already describe this file - nothing to do.
            if (
                record.width == measured["width"]
                and record.height == measured["height"]
                and record.file_size_bytes == measured["file_size_bytes"]
            ):
                continue

            logger.info(
                "Repairing stale metrics for %s: %sx%s -> %sx%s",
                record.id,
                record.width,
                record.height,
                measured["width"],
                measured["height"],
            )
            record_metrics.refresh_delivery_metrics(record)
            repaired += 1

        if repaired:
            db.commit()
            logger.info("Repaired delivery metrics for %d record(s)", repaired)
    except Exception:  # pragma: no cover - a repair must never block startup
        db.rollback()
        logger.exception("Delivery-metric repair failed; leaving records untouched")
        return 0
    finally:
        db.close()

    return repaired


def run_metric_repairs(engine: Engine) -> int:
    """Entry point for startup: run the repair against the app's session factory.

    ``engine`` is accepted to match the signature of the other startup helpers and
    to make the call site read consistently; the session factory is bound to the
    same engine by ``database``.
    """
    from database import SessionLocal

    return repair_delivery_metrics(SessionLocal)
