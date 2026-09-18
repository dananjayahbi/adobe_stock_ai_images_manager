"""Approve router - handles record approval actions."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import ImageRecord, ImageStatus
from schemas import ApproveRequest, ApproveResponse
from tasks.audit_orchestrator import process_approval

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approve"])


@router.post("/api/records/{record_id}/approve", response_model=ApproveResponse)
async def approve_record(
    record_id: str,
    request: ApproveRequest | None = None,
    db: Session = Depends(get_db),
) -> ApproveResponse:
    """Approve a PASSED or FLAGGED record, triggering metadata embedding and staging."""
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")

    # Idempotency: already-finalized records return success without side effects.
    if record.status == ImageStatus.READY:
        return ApproveResponse(
            record_id=record.id,
            status=record.status,
            title=record.generated_title,
            keywords_count=len(record.generated_keywords or []),
        )

    if record.status in (ImageStatus.PENDING, ImageStatus.AUDITING):
        raise HTTPException(
            status_code=400,
            detail=f"Record is in {record.status.value} state and cannot be approved yet.",
        )

    if record.status not in (ImageStatus.PASSED, ImageStatus.FLAGGED, ImageStatus.APPROVED):
        raise HTTPException(
            status_code=400,
            detail=f"Record is in {record.status.value} state and cannot be approved.",
        )

    override_metadata = None
    if request and (request.override_title or request.override_description or request.override_keywords):
        override_metadata = {
            "title": request.override_title or "",
            "description": request.override_description or "",
            "keywords": request.override_keywords or [],
        }

    success = process_approval(
        db_session_factory=SessionLocal,
        record_id=record_id,
        settings=settings,
        override_metadata=override_metadata,
    )
    if not success:
        raise HTTPException(
            status_code=502,
            detail="Approval pipeline failed (metadata generation, file copy, or embedding).",
        )

    db.expire_all()
    refreshed = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not refreshed:
        raise HTTPException(status_code=500, detail="Record disappeared during approval.")

    return ApproveResponse(
        record_id=refreshed.id,
        status=refreshed.status,
        title=refreshed.generated_title,
        keywords_count=len(refreshed.generated_keywords or []),
    )
