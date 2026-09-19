"""Records router - handles listing and retrieving image records."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import ImageRecord, ImageStatus
from schemas import RecordListResponse, RecordResponse

router = APIRouter(tags=["records"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

# Gallery usage filter values accepted by the `used` query parameter.
USED_FILTERS = ("all", "used", "unused")


@router.get("/api/records", response_model=RecordListResponse)
async def list_records(
    status: str | None = Query(default=None, description="Filter by pipeline state."),
    used: str = Query(
        default="all",
        description="Usage filter for the gallery: 'all', 'used', or 'unused'.",
    ),
    ids: str | None = Query(
        default=None,
        description="Comma-separated record ids to fetch explicitly.",
    ),
    limit: int = Query(default=DEFAULT_LIMIT, description="Max records to return."),
    offset: int = Query(default=0, description="Records to skip for pagination."),
    db: Session = Depends(get_db),
) -> RecordListResponse:
    """Return records newest-first with optional status/usage filtering."""
    if limit < 0 or offset < 0:
        raise HTTPException(
            status_code=400, detail="Pagination values must be non-negative."
        )
    if limit > MAX_LIMIT:
        raise HTTPException(
            status_code=400, detail=f"Limit exceeds the maximum of {MAX_LIMIT}."
        )

    used_filter = (used or "all").lower()
    if used_filter not in USED_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid usage filter. Accepted values: {', '.join(USED_FILTERS)}.",
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

    id_filter: list[str] = []
    if ids:
        id_filter = [value.strip() for value in ids.split(",") if value.strip()]

    base = select(ImageRecord)
    count_stmt = select(func.count()).select_from(ImageRecord)

    if status_filter is not None:
        base = base.where(ImageRecord.status == status_filter)
        count_stmt = count_stmt.where(ImageRecord.status == status_filter)

    if used_filter == "used":
        base = base.where(ImageRecord.is_used.is_(True))
        count_stmt = count_stmt.where(ImageRecord.is_used.is_(True))
    elif used_filter == "unused":
        base = base.where(ImageRecord.is_used.is_(False))
        count_stmt = count_stmt.where(ImageRecord.is_used.is_(False))

    if id_filter:
        base = base.where(ImageRecord.id.in_(id_filter))
        count_stmt = count_stmt.where(ImageRecord.id.in_(id_filter))

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


@router.get("/api/records/{record_id}", response_model=RecordResponse)
async def get_record(record_id: str, db: Session = Depends(get_db)) -> RecordResponse:
    """Return a single record by id."""
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")
    return RecordResponse.model_validate(record)
