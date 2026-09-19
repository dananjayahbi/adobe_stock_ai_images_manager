"""Explicit stage-queue endpoints.

Records are *pushed* into a stage's queue without being processed: the push
records intent, and the destination page shows those records in a "draft"
bucket until the operator runs the stage.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import ImageRecord
from schemas import BulkActionResult, DeleteRequest

router = APIRouter(tags=["queues"])

#: Stage keys a record can be pushed into. Deliberately a separate namespace
#: from ``PipelineStage`` - the queue holds intent, not workflow position.
VALID_QUEUE_KEYS = frozenset(
    {"ocr", "upscale", "refine", "compatibility", "metadata", "gallery"}
)

#: Maximum records accepted by one push/remove call.
MAX_BATCH_SIZE = 500


def _validate_stage_key(stage_key: str) -> str:
    """Reject a stage key that is not a known queue destination."""
    if stage_key not in VALID_QUEUE_KEYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown stage '{stage_key}'. "
                f"Valid keys: {', '.join(sorted(VALID_QUEUE_KEYS))}."
            ),
        )
    return stage_key


def _validate_ids(record_ids: list[str]) -> list[str]:
    """De-duplicate ids while preserving order and enforcing the batch cap."""
    unique = list(dict.fromkeys(record_ids))
    if not unique:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(unique) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process more than {MAX_BATCH_SIZE} records at once.",
        )
    return unique


def _apply_queue(
    db: Session, record_ids: list[str], value: str | None
) -> BulkActionResult:
    """Set ``queued_stage`` to ``value`` on every record that exists."""
    records = db.query(ImageRecord).filter(ImageRecord.id.in_(record_ids)).all()
    found = {record.id for record in records}
    for record in records:
        record.queued_stage = value
    db.commit()
    missing = [rid for rid in record_ids if rid not in found]
    return BulkActionResult(updated=len(records), missing=missing)


# --------------------------------------------------------------------------- #
# Queue mutation
# --------------------------------------------------------------------------- #

@router.post("/api/queues/{stage_key}/push", response_model=BulkActionResult)
async def push_to_queue(
    stage_key: str,
    request: DeleteRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Mark records as awaiting ``stage_key`` without running it.

    Idempotent: pushing an already-queued record re-sets the same value and
    still counts as updated.
    """
    _validate_stage_key(stage_key)
    record_ids = _validate_ids(request.record_ids)
    return _apply_queue(db, record_ids, stage_key)


@router.post("/api/queues/{stage_key}/remove", response_model=BulkActionResult)
async def remove_from_queue(
    stage_key: str,
    request: DeleteRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Clear the queue entry for records the operator no longer wants pushed."""
    _validate_stage_key(stage_key)
    record_ids = _validate_ids(request.record_ids)
    return _apply_queue(db, record_ids, None)


# --------------------------------------------------------------------------- #
# Queue summary
# --------------------------------------------------------------------------- #

@router.get("/api/queues/summary")
async def queue_summary(db: Session = Depends(get_db)) -> dict:
    """Pending queue depth per stage key, zero-filled for every valid key."""
    rows = (
        db.query(ImageRecord.queued_stage, func.count(ImageRecord.id))
        .filter(ImageRecord.queued_stage.isnot(None))
        .group_by(ImageRecord.queued_stage)
        .all()
    )
    counts = {key: 0 for key in sorted(VALID_QUEUE_KEYS)}
    for queued_stage, count in rows:
        key = queued_stage if isinstance(queued_stage, str) else str(queued_stage)
        counts[key] = counts.get(key, 0) + count
    return {"counts": counts, "total": sum(counts.values())}
