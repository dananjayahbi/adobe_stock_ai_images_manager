"""Promote router - the gallery's manual "push to ready-to-upload" override.

Endpoints:
* ``POST /api/promote/check`` - pre-flight: which requirements are missing
  per record (nothing runs, nothing is written).
* ``POST /api/promote/run``   - run only the missing steps per record, then
  promote the ones that end up passing (background job; poll ``/api/jobs/{id}``).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import ImageRecord
from schemas import (
    JobResponse,
    PromoteCheckRequest,
    PromoteCheckResponse,
    PromoteRunRequest,
)
from services import promote
from services.jobs import JobItem, registry
from tasks import promote_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["promote"])

MAX_PROMOTE_BATCH = 500


def _validate_ids(record_ids: list[str]) -> list[str]:
    unique = list(dict.fromkeys(record_ids))
    if not unique:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(unique) > MAX_PROMOTE_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot promote more than {MAX_PROMOTE_BATCH} records at once.",
        )
    return unique


def _run_promote_job(
    record_ids: list[str],
    kwargs: dict,
) -> None:
    """Dispatch the promote orchestrator, making a crash visible on the job."""
    job_id = kwargs.get("job_id")
    try:
        promote_orchestrator.promote_records(SessionLocal, record_ids, settings, **kwargs)
    except Exception as exc:  # noqa: BLE001 - must not escape into the task runner
        logger.exception("Promote job crashed before completing")
        job = registry.get(job_id) if job_id else None
        if job is None:
            return
        for item in job.items:
            if item.status in ("pending", "running"):
                item.status = "failed"
                item.message = f"The promote job could not start: {type(exc).__name__}: {exc}"
        registry.finish(job, "failed")


@router.post("/api/promote/check", response_model=PromoteCheckResponse)
async def promote_check(
    request: PromoteCheckRequest,
    db: Session = Depends(get_db),
) -> PromoteCheckResponse:
    """Pre-flight the selection: report missing requirements per record."""
    record_ids = _validate_ids(request.record_ids)

    records = db.query(ImageRecord).filter(ImageRecord.id.in_(record_ids)).all()
    by_id = {record.id: record for record in records}
    ordered = [by_id[rid] for rid in record_ids if rid in by_id]
    missing = [rid for rid in record_ids if rid not in by_id]
    if not ordered and missing:
        raise HTTPException(status_code=404, detail="None of the given records exist.")

    return PromoteCheckResponse(
        items=[promote.evaluate_record(record) for record in ordered],
        missing=missing,
    )


@router.post("/api/promote/run", response_model=JobResponse)
async def promote_run(
    request: PromoteRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobResponse:
    """Run the missing promote steps and move passing records to Stage 6."""
    record_ids = _validate_ids(request.record_ids)

    records = db.query(ImageRecord).filter(ImageRecord.id.in_(record_ids)).all()
    by_id = {record.id: record for record in records}
    ordered = [by_id[rid] for rid in record_ids if rid in by_id]
    if not ordered:
        raise HTTPException(status_code=404, detail="None of the given records exist.")

    job = registry.create(
        "promote",
        "promote-ready",
        [
            JobItem(record_id=record.id, filename=record.filename)
            for record in ordered
        ],
    )

    background_tasks.add_task(
        _run_promote_job,
        [record.id for record in ordered],
        {
            "job_id": job.id,
            "use_semantic": request.use_semantic,
        },
    )

    return JobResponse(**job.to_dict())
