"""Approve router - fast state flips for the publish queue.

Approving used to run the whole approval pipeline (LLM metadata generation,
file copy, ExifTool embedding, a second session), which held the HTTP request
open for up to 240s. Publishing (Stage 7) now owns that work via
``tasks.audit_orchestrator.process_approval``; this endpoint only moves the
record's lifecycle state, so it answers immediately.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ImageLifecycleState, ImageRecord
from schemas import ApproveRequest, ApproveResponse, RecordResponse, StateChangeRequest
from services.image_lifecycle import ALLOWED_STATE_TRANSITIONS, apply_state_change

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approve"])

#: States that already passed through the approve gate: approving again is an
#: idempotent no-op rather than an error (mirrors the old READY idempotency).
APPROVED_ALREADY: frozenset[ImageLifecycleState] = frozenset(
    {
        ImageLifecycleState.READY_TO_PUBLISH,
        ImageLifecycleState.PUBLISHED,
        ImageLifecycleState.AS_ACCEPTED,
    }
)

#: States the approve action may queue for publish.
QUEUEABLE_STATES: frozenset[ImageLifecycleState] = frozenset(
    {ImageLifecycleState.APPROVED, ImageLifecycleState.REJECTED}
)


def _approve_response(record: ImageRecord) -> ApproveResponse:
    return ApproveResponse(
        record_id=record.id,
        status=record.status,
        state=record.state,
        title=record.generated_title,
        keywords_count=len(record.generated_keywords or []),
    )


@router.post("/api/records/{record_id}/approve", response_model=ApproveResponse)
async def approve_record(
    record_id: str,
    request: ApproveRequest | None = None,
    db: Session = Depends(get_db),
) -> ApproveResponse:
    """Queue an APPROVED or REJECTED record for publish (state flip only).

    No metadata generation, no file copy, no embedding — one UPDATE and out.
    Records already queued (or further along) return success unchanged.
    ``request`` overrides are accepted for wire compatibility but no longer
    applied: metadata is produced earlier, by Stage 6.
    """
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")

    if record.state in APPROVED_ALREADY:
        return _approve_response(record)

    if record.state not in QUEUEABLE_STATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Record is in {record.state.value} state and cannot be queued "
                "for publish yet."
            ),
        )

    record.state = ImageLifecycleState.READY_TO_PUBLISH
    db.commit()

    refreshed = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not refreshed:
        raise HTTPException(status_code=500, detail="Record disappeared during approval.")
    return _approve_response(refreshed)


@router.patch("/api/records/{record_id}/state", response_model=RecordResponse)
async def change_record_state(
    record_id: str,
    request: StateChangeRequest,
    db: Session = Depends(get_db),
) -> RecordResponse:
    """Move a record between lifecycle states along the manual whitelist.

    Unknown values and disallowed transitions are 400s that say exactly what
    would have been accepted, rather than a silently ignored change.
    """
    try:
        target = ImageLifecycleState(request.state)
    except ValueError:
        allowed = ", ".join(state.value for state in ImageLifecycleState)
        raise HTTPException(
            status_code=400, detail=f"Invalid state. Accepted values: {allowed}."
        )

    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")

    if not apply_state_change(record, target):
        allowed_targets = ALLOWED_STATE_TRANSITIONS.get(record.state, frozenset())
        allowed_to = ", ".join(sorted(state.value for state in allowed_targets))
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot change state from {record.state.value} to {target.value}. "
                f"Allowed from {record.state.value}: {allowed_to or 'nothing'}."
            ),
        )

    db.commit()
    db.refresh(record)
    return RecordResponse.model_validate(record)
