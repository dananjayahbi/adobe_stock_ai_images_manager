"""Prompt Library endpoints.

Stage 1 has two modes: *Advanced* (prompt-first — write prompts, then bind the
images they produced) and *Quick* (upload-first, the original behaviour). This
router serves the Advanced mode's data.

The endpoints are deliberately separate from ``/api/records``: a prompt is a
first-class artifact, not a property of an image. Binding is a mutation on the
*images*, so it lives here with the prompt as the subject.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from models import ImageRecord, Prompt, PromptStatus
from schemas import (
    PromptBindRequest,
    PromptBindResponse,
    PromptCreateRequest,
    PromptListResponse,
    PromptResponse,
    PromptUpdateRequest,
)
from services import prompt_library

router = APIRouter(tags=["prompts"])

#: Maximum records one bind call may touch.
MAX_BIND_BATCH = 500

#: Accepted ``status`` filters. See ``services.prompt_library.LIST_FILTERS``.
STATUS_FILTERS = prompt_library.LIST_FILTERS


def _get_prompt_or_404(db: Session, prompt_id: str) -> Prompt:
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise HTTPException(
            status_code=404, detail=f"Prompt {prompt_id} does not exist."
        )
    return prompt


def _bound_count(db: Session, prompt_id: str) -> int:
    return db.execute(
        select(func.count(ImageRecord.id)).where(ImageRecord.prompt_id == prompt_id)
    ).scalar_one()


def _response(db: Session, prompt: Prompt) -> PromptResponse:
    """Serialise a prompt with its freshly counted bindings."""
    count = _bound_count(db, prompt.id)
    return PromptResponse.model_validate(
        prompt_library.prompt_to_dict(prompt, bound_count=count)
    )


def _validate_ids(record_ids: list[str]) -> list[str]:
    """De-duplicate ids while preserving order and enforcing the batch cap."""
    unique = list(dict.fromkeys(record_ids))
    if not unique:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(unique) > MAX_BIND_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot bind more than {MAX_BIND_BATCH} records at once.",
        )
    return unique


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #

@router.get("/api/prompts", response_model=PromptListResponse)
async def list_prompts(
    status: str = Query(
        default="all",
        description=(
            "Filter by library state: 'all', 'draft', 'used', 'unused', "
            "'bound', 'unbound', or 'archived'. The status filters ('draft', "
            "'used', 'unused', 'archived') read the stored prompt status; "
            "'bound'/'unbound' read whether any image is linked to it. A prompt "
            "can be used without being bound, so the two axes are independent."
        ),
    ),
    db: Session = Depends(get_db),
) -> PromptListResponse:
    """Return every prompt newest-first with its binding count.

    The ``used``/``unused`` split is derived from the stored status, while
    ``bound``/``unbound`` is derived from the actual bindings. Keeping them
    separate is what lets the operator answer two different questions: "have I
    consumed this prompt?" and "have I collected what it produced?".
    """
    key = (status or "all").lower()
    if key not in STATUS_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Accepted values: {', '.join(STATUS_FILTERS)}.",
        )

    counts = prompt_library.binding_counts(db)
    prompts = list(
        db.execute(select(Prompt).order_by(Prompt.created_at.desc())).scalars().all()
    )

    items: list[PromptResponse] = []
    for prompt in prompts:
        bound = counts.get(prompt.id, 0)
        if not prompt_library.matches_filter(prompt, bound, key):
            continue
        items.append(
            PromptResponse.model_validate(
                prompt_library.prompt_to_dict(prompt, bound_count=bound)
            )
        )

    totals = prompt_library.library_totals(db)
    return PromptListResponse(items=items, **totals)


@router.get("/api/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(prompt_id: str, db: Session = Depends(get_db)) -> PromptResponse:
    """Return one prompt with its binding count."""
    return _response(db, _get_prompt_or_404(db, prompt_id))


# --------------------------------------------------------------------------- #
# Mutation
# --------------------------------------------------------------------------- #

@router.post("/api/prompts", response_model=PromptResponse, status_code=201)
async def create_prompt(
    request: PromptCreateRequest,
    db: Session = Depends(get_db),
) -> PromptResponse:
    """Create a prompt from the sidebar editor.

    An empty title is filled in from the body, because the operator usually
    writes the prompt text first and a blank title would render as an unlabelled
    block in the library.
    """
    body = (request.body or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="A prompt body is required.")

    title = (request.title or "").strip() or prompt_library.derive_title(body)
    prompt = Prompt(
        title=title,
        body=body,
        negative_prompt=(request.negative_prompt or "").strip() or None,
        params=request.params,
        tags=prompt_library.normalise_tags(request.tags),
        status=request.status or PromptStatus.DRAFT,
    )
    if prompt.status == PromptStatus.USED:
        prompt.used_at = datetime.now(timezone.utc)

    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    return _response(db, prompt)


@router.patch("/api/prompts/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: str,
    request: PromptUpdateRequest,
    db: Session = Depends(get_db),
) -> PromptResponse:
    """Edit a prompt, or mark it used/draft/archived by hand.

    ``exclude_unset`` is what makes this a real PATCH: a field the client did
    not send is left alone, so clearing a negative prompt requires sending an
    explicit empty string.
    """
    prompt = _get_prompt_or_404(db, prompt_id)
    payload = request.model_dump(exclude_unset=True)

    if "body" in payload:
        body = (payload["body"] or "").strip()
        if not body:
            raise HTTPException(status_code=400, detail="A prompt body is required.")
        prompt.body = body

    if "title" in payload:
        title = (payload["title"] or "").strip()
        # An explicitly blank title falls back to the derived one rather than
        # leaving an unlabelled block.
        prompt.title = title or prompt_library.derive_title(prompt.body)

    if "negative_prompt" in payload:
        prompt.negative_prompt = (payload["negative_prompt"] or "").strip() or None

    if "params" in payload:
        prompt.params = payload["params"]

    if "tags" in payload:
        prompt.tags = prompt_library.normalise_tags(payload["tags"])

    if "status" in payload and payload["status"] is not None:
        prompt.status = payload["status"]
        if prompt.status == PromptStatus.USED and prompt.used_at is None:
            prompt.used_at = datetime.now(timezone.utc)
        elif prompt.status == PromptStatus.DRAFT:
            prompt.used_at = None

    db.commit()
    db.refresh(prompt)

    # A hand-set DRAFT that still has bound images is inconsistent, so the
    # derived rule wins: binding implies used.
    prompt_library.sync_used_status(db, prompt)
    db.commit()
    db.refresh(prompt)

    return _response(db, prompt)


@router.delete("/api/prompts/{prompt_id}")
async def delete_prompt(prompt_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a prompt and unbind it from its images.

    The images are deliberately **kept**. Deleting a prompt must not delete the
    assets it produced — the operator would lose collectible work over a
    bookkeeping decision. Their ``prompt_id`` is cleared instead.
    """
    prompt = _get_prompt_or_404(db, prompt_id)
    unbound = (
        db.query(ImageRecord)
        .filter(ImageRecord.prompt_id == prompt_id)
        .update({ImageRecord.prompt_id: None}, synchronize_session=False)
    )
    db.delete(prompt)
    db.commit()
    return {"deleted": 1, "unbound": int(unbound or 0)}


# --------------------------------------------------------------------------- #
# Binding
# --------------------------------------------------------------------------- #

@router.post("/api/prompts/{prompt_id}/bind", response_model=PromptBindResponse)
async def bind_prompt(
    prompt_id: str,
    request: PromptBindRequest,
    db: Session = Depends(get_db),
) -> PromptBindResponse:
    """Bind images to a prompt (or unbind them).

    This is the endpoint behind dragging a prompt block onto an image. Binding
    is many-to-one — one prompt, many images — so re-binding an image that
    already points at another prompt simply re-points it, and the previous
    prompt's status is re-synced so it does not stay USED with zero images.
    """
    prompt = _get_prompt_or_404(db, prompt_id)
    record_ids = _validate_ids(request.record_ids)

    records = db.query(ImageRecord).filter(ImageRecord.id.in_(record_ids)).all()
    found = {record.id for record in records}

    previous_prompt_ids: set[str] = set()
    rebound: list[str] = []

    for record in records:
        previous = record.prompt_id
        if not request.unbind and previous and previous != prompt_id:
            previous_prompt_ids.add(previous)
            rebound.append(record.id)
        elif previous and previous != prompt_id:
            previous_prompt_ids.add(previous)
        record.prompt_id = None if request.unbind else prompt_id

    # Flush before re-syncing: `sync_used_status` counts bound rows with a
    # query, and the session runs with autoflush disabled, so without this the
    # count would still see the pre-bind state and the prompt would stay DRAFT.
    db.flush()

    # Re-sync every prompt that lost an image, so a prompt whose last binding
    # moved away is not left claiming images it no longer has.
    for other_id in previous_prompt_ids:
        other = db.query(Prompt).filter(Prompt.id == other_id).first()
        if other is not None:
            prompt_library.sync_used_status(db, other)

    if not request.unbind:
        prompt_library.sync_used_status(db, prompt)

    db.commit()
    db.refresh(prompt)
    return PromptBindResponse(
        updated=len(records),
        missing=[rid for rid in record_ids if rid not in found],
        rebound=rebound,
        prompt=_response(db, prompt),
    )
