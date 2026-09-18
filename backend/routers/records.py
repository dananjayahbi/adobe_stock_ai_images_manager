"""Records router - handles listing and retrieving image records."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import ImageRecord, ImageStatus
from schemas import RecordListResponse

router = APIRouter(tags=["records"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


@router.get("/api/records", response_model=RecordListResponse)
async def list_records(
    status: str | None = Query(default=None, description="Filter by pipeline state."),
    limit: int = Query(default=DEFAULT_LIMIT, description="Max records to return."),
    offset: int = Query(default=0, description="Records to skip for pagination."),
    db: Session = Depends(get_db),
) -> RecordListResponse:
    """Return records newest-first with optional status filtering and pagination."""
    if limit < 0 or offset < 0:
        raise HTTPException(
            status_code=400, detail="Pagination values must be non-negative."
        )
    if limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"Limit exceeds the maximum of {MAX_LIMIT}."
        )

    status_filter: ImageStatus | None = None
    if status is not None:
        try:
            status_filter = ImageStatus(status)
        except ValueError:
            allowed = ", ".join(s.value for s in ImageStatus)
            raise HTTPException(
                status_code=400, detail=f"Invalid status. Accepted values: {allowed}."
            )

    base = select(ImageRecord)
    count_stmt = select(func.count()).select_from(ImageRecord)
    if status_filter is not None:
        base = base.where(ImageRecord.status == status_filter)
        count_stmt = count_stmt.where(ImageRecord.status == status_filter)

    total = db.execute(count_stmt).scalar_one()
    stmt = (
        base.order_by(ImageRecord.created_at.desc())
        .offset(offset)
        .limit(min(limit, MAX_LIMIT))
    )
    records = list(db.execute(stmt).scalars().all())

    page_size = limit if limit > 0 else DEFAULT_LIMIT
    page = (offset // page_size) + 1 if page_size else 1

    return RecordListResponse(
        items=records,
        total=total,
        page=page,
        page_size=page_size,
    )
