"""Promote orchestrator - batch driver for the manual ready-to-upload push.

Mirrors ``stage_orchestrator``: one job, one item per record, per-record
failures never abort the batch, and outcomes are persisted before the next
record starts. Each record only runs the steps it is actually missing.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from config import Settings, settings as default_settings
from models import ImageRecord
from services import promote
from services.jobs import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    Job,
    JobItem,
    registry,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def _load_records(
    db: Session, record_ids: Iterable[str]
) -> tuple[list[ImageRecord], list[str]]:
    ids = list(dict.fromkeys(record_ids))
    if not ids:
        return [], []
    records = db.query(ImageRecord).filter(ImageRecord.id.in_(ids)).all()
    by_id = {record.id: record for record in records}
    ordered = [by_id[rid] for rid in ids if rid in by_id]
    missing = [rid for rid in ids if rid not in by_id]
    return ordered, missing


def _start_job(
    job_id: str | None, records: list[ImageRecord]
) -> Job:
    if job_id:
        existing = registry.get(job_id)
        if existing is not None:
            return existing
    return registry.create(
        "promote",
        "promote-ready",
        [
            JobItem(record_id=record.id, filename=record.filename)
            for record in records
        ],
    )


def promote_records(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    use_semantic: bool = False,
    job_id: str | None = None,
) -> str:
    """Run the missing promote steps per record, then move each to Stage 6.

    Returns the job id.
    """
    cfg = settings or default_settings
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, records)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if job.cancel_requested:
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            evaluation = promote.evaluate_record(record)
            if evaluation["blocker"]:
                item.status = "skipped"
                item.message = evaluation["blocker"]
                item.finished_at = time.time()
                continue

            # Re-fetch the ORM object on this session: run_missing_steps
            # commits, which expires the instance; the loop's other reads go
            # through the same identity map so a stale rollback cannot leak
            # one record's edits into the next.
            try:
                promoted, messages = promote.run_missing_steps(
                    db, record, cfg, use_semantic=use_semantic
                )
                item.message = " ".join(messages)
                if promoted:
                    item.status = "succeeded"
                    item.score = record.acceptance_score
                else:
                    item.status = "failed"
            except Exception as exc:  # noqa: BLE001 - one bad record must not stop the batch
                logger.exception("Promote failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Promote error: {exc}"
            finally:
                item.progress = 100.0
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    except Exception:
        # A crash before finish() would leave the job "running" forever.
        if job is not None:
            for item in job.items:
                if item.status in ("pending", "running"):
                    item.status = "failed"
                    item.message = "The promote job crashed."
                    item.finished_at = time.time()
            registry.finish(job, STATUS_FAILED)
        raise
    finally:
        db.close()
