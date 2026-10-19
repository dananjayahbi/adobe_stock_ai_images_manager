"""Records router - handles listing and retrieving image records."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import ImageLifecycleState, ImageRecord, ImageStatus, PipelineStage
from schemas import RecordListResponse, RecordResponse

router = APIRouter(tags=["records"])

DEFAULT_LIMIT = 100
MAX_LIMIT = 500

#: Longest accepted search term. A search is a UI affordance, not a report
#: generator, and an unbounded pattern makes the `LIKE` scan arbitrarily wide.
MAX_SEARCH_LENGTH = 200

# Gallery usage filter values accepted by the `used` query parameter.
USED_FILTERS = ("all", "used", "unused")

#: ``queued`` sentinel that selects records with no pending stage queue entry.
QUEUED_NONE_SENTINEL = "none"

#: ``prompt_id`` sentinel that selects records with no bound source prompt.
PROMPT_NONE_SENTINEL = "none"

#: Valid values for the ``stage`` filter, taken from the enum so the two cannot
#: drift. A typo in a query string is reported rather than silently matching
#: nothing, which would look like "the filter is broken".
_PIPELINE_STAGE_VALUES: frozenset[str] = frozenset(stage.value for stage in PipelineStage)

#: Valid values for the ``state`` filter — same reasoning as the stage set:
#: a typo is reported instead of silently matching nothing.
_LIFECYCLE_STATE_VALUES: frozenset[str] = frozenset(
    state.value for state in ImageLifecycleState
)

#: SQL type used to cast JSON and integer columns to text for a substring match.
_TEXT = String()


def _search_condition(term: str):
    """Match ``term`` against every text field a user would search by.

    Deliberately broad, because the operator searching the published gallery is
    looking for *an image they remember*, and they may recall it by its title, a
    keyword, the category, or the filename they set for the upload. Searching
    only the title would fail for the two cases that matter most: a keyword that
    never made it into the title, and the delivered filename.

    ``keywords`` is a JSON column. SQLite has no JSON operators guaranteed to be
    present, so it is matched as text - which is exactly right here, since the
    stored form is a JSON array of plain strings and a substring match on it
    finds a keyword without needing to unpack it.
    """
    pattern = f"%{term.lower()}%"
    return or_(
        func.lower(func.coalesce(ImageRecord.generated_title, "")).like(pattern),
        func.lower(func.coalesce(ImageRecord.generated_description, "")).like(pattern),
        func.lower(func.coalesce(ImageRecord.filename, "")).like(pattern),
        func.lower(func.coalesce(ImageRecord.download_name, "")).like(pattern),
        func.lower(func.coalesce(ImageRecord.suggested_filename, "")).like(pattern),
        func.lower(func.coalesce(func.cast(ImageRecord.generated_keywords, _TEXT), "")).like(
            pattern
        ),
        func.cast(ImageRecord.category, _TEXT).like(pattern),
    )


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
    queued: str | None = Query(
        default=None,
        description=(
            "Filter by pending stage queue: a stage key, or 'none' for "
            "records that are not queued anywhere."
        ),
    ),
    prompt_id: str | None = Query(
        default=None,
        description=(
            "Filter by the Prompt Library link: a prompt id, or 'none' for "
            "images with no known source prompt."
        ),
    ),
    stage: str | None = Query(
        default=None,
        description=(
            "Comma-separated pipeline stages to include, e.g. 'PUBLISHED'. "
            "Used by the published gallery to scope itself to finished assets."
        ),
    ),
    state: str | None = Query(
        default=None,
        description=(
            "Comma-separated lifecycle states to include, e.g. "
            "'READY_TO_PUBLISH,PUBLISHED'."
        ),
    ),
    search: str | None = Query(
        default=None,
        description=(
            "Case-insensitive substring match across the title, description, "
            "keywords, category and filename."
        ),
    ),
    stage_updated: bool = Query(
        default=False,
        description=(
            "When true, only return records a pipeline step has actually "
            "touched (stage_updated_at is set) — the new UI's 'processed' "
            "definition for home and gallery."
        ),
    ),
    group_id: str | None = Query(
        default=None,
        description=(
            "Gallery folder filter: a group id, or 'none' for ungrouped "
            "images. Filters apply to images only — groups themselves are "
            "listed by GET /api/groups."
        ),
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

    if queued:
        if queued == QUEUED_NONE_SENTINEL:
            base = base.where(ImageRecord.queued_stage.is_(None))
            count_stmt = count_stmt.where(ImageRecord.queued_stage.is_(None))
        else:
            base = base.where(ImageRecord.queued_stage == queued)
            count_stmt = count_stmt.where(ImageRecord.queued_stage == queued)

    if prompt_id:
        if prompt_id == PROMPT_NONE_SENTINEL:
            base = base.where(ImageRecord.prompt_id.is_(None))
            count_stmt = count_stmt.where(ImageRecord.prompt_id.is_(None))
        else:
            base = base.where(ImageRecord.prompt_id == prompt_id)
            count_stmt = count_stmt.where(ImageRecord.prompt_id == prompt_id)

    if id_filter:
        base = base.where(ImageRecord.id.in_(id_filter))
        count_stmt = count_stmt.where(ImageRecord.id.in_(id_filter))

    if stage:
        stage_filter = [value.strip().upper() for value in stage.split(",") if value.strip()]
        invalid_stages = [
            value for value in stage_filter if value not in _PIPELINE_STAGE_VALUES
        ]
        if invalid_stages:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid stage(s): {', '.join(invalid_stages)}. Accepted "
                    f"values: {', '.join(sorted(_PIPELINE_STAGE_VALUES))}."
                ),
            )
        if stage_filter:
            base = base.where(ImageRecord.stage.in_(stage_filter))
            count_stmt = count_stmt.where(ImageRecord.stage.in_(stage_filter))

    if state:
        state_filter = [
            value.strip().upper() for value in state.split(",") if value.strip()
        ]
        invalid_states = [
            value for value in state_filter if value not in _LIFECYCLE_STATE_VALUES
        ]
        if invalid_states:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid state(s): {', '.join(invalid_states)}. Accepted "
                    f"values: {', '.join(sorted(_LIFECYCLE_STATE_VALUES))}."
                ),
            )
        parsed_states = [ImageLifecycleState(value) for value in state_filter]
        base = base.where(ImageRecord.state.in_(parsed_states))
        count_stmt = count_stmt.where(ImageRecord.state.in_(parsed_states))

    if search and search.strip():
        term = search.strip()
        if len(term) > MAX_SEARCH_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Search term exceeds {MAX_SEARCH_LENGTH} characters.",
            )
        condition = _search_condition(term)
        base = base.where(condition)
        count_stmt = count_stmt.where(condition)

    if stage_updated:
        condition = ImageRecord.stage_updated_at.isnot(None)
        base = base.where(condition)
        count_stmt = count_stmt.where(condition)

    if group_id is not None:
        if group_id == QUEUED_NONE_SENTINEL:
            condition = ImageRecord.group_id.is_(None)
        else:
            condition = ImageRecord.group_id == group_id
        base = base.where(condition)
        count_stmt = count_stmt.where(condition)

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
