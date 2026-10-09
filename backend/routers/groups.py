"""Gallery folders (groups) - create, rename, delete, and move images.

A folder is a flat, hand-maintained label: ``ImageRecord.group_id`` is the
only edge, so moving an image between folders is a one-column update and
deleting a folder simply releases its images back to the top level. Images are
never deleted with their folder.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import ImageGroup, ImageRecord
from schemas import (
    BulkActionResult,
    GroupAssignRequest,
    GroupCreateRequest,
    GroupListResponse,
    GroupRenameRequest,
    GroupResponse,
)

router = APIRouter(tags=["gallery-groups"])

MAX_GROUPS = 200
MAX_NAME_LENGTH = 200


def _clean_name(raw: str) -> str:
    name = " ".join((raw or "").split())
    if not name:
        raise HTTPException(status_code=400, detail="Group name must not be empty.")
    return name[:MAX_NAME_LENGTH]


def _get_group_or_404(db: Session, group_id: str) -> ImageGroup:
    group = db.get(ImageGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group {group_id} does not exist.")
    return group


def _counts_by_group(db: Session) -> dict[str, int]:
    """One aggregate query - never one COUNT per folder."""
    rows = (
        db.query(ImageRecord.group_id, func.count(ImageRecord.id))
        .group_by(ImageRecord.group_id)
        .all()
    )
    return {group_id: count for group_id, count in rows if group_id}


def _to_response(group: ImageGroup, counts: dict[str, int]) -> GroupResponse:
    return GroupResponse(
        id=group.id,
        name=group.name,
        image_count=counts.get(group.id, 0),
        created_at=group.created_at,
    )


@router.get("/api/groups", response_model=GroupListResponse)
async def list_groups(db: Session = Depends(get_db)) -> GroupListResponse:
    """Every folder with its live image count, oldest-first."""
    groups = db.query(ImageGroup).order_by(ImageGroup.created_at).all()
    counts = _counts_by_group(db)
    return GroupListResponse(items=[_to_response(g, counts) for g in groups])


@router.post("/api/groups", response_model=GroupResponse, status_code=201)
async def create_group(
    request: GroupCreateRequest,
    db: Session = Depends(get_db),
) -> GroupResponse:
    """Create a folder, optionally moving the given images into it at once."""
    name = _clean_name(request.name)
    total = db.query(func.count(ImageGroup.id)).scalar() or 0
    if total >= MAX_GROUPS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create more than {MAX_GROUPS} groups.",
        )

    group = ImageGroup(name=name)
    db.add(group)
    db.flush()  # assign the id before any record references it

    updated = 0
    if request.record_ids:
        records = (
            db.query(ImageRecord)
            .filter(ImageRecord.id.in_(request.record_ids))
            .all()
        )
        for record in records:
            record.group_id = group.id
            updated += 1

    db.commit()
    db.refresh(group)
    return _to_response(group, {group.id: updated})


@router.patch("/api/groups/{group_id}", response_model=GroupResponse)
async def rename_group(
    group_id: str,
    request: GroupRenameRequest,
    db: Session = Depends(get_db),
) -> GroupResponse:
    """Rename a folder. Membership is untouched."""
    group = _get_group_or_404(db, group_id)
    group.name = _clean_name(request.name)
    db.commit()
    return _to_response(group, _counts_by_group(db))


@router.delete("/api/groups/{group_id}", response_model=GroupResponse)
async def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
) -> GroupResponse:
    """Delete the folder only - its images fall back to the top level."""
    group = _get_group_or_404(db, group_id)
    response = _to_response(group, _counts_by_group(db))
    db.query(ImageRecord).filter(ImageRecord.group_id == group_id).update(
        {"group_id": None}
    )
    db.delete(group)
    db.commit()
    return response


@router.put("/api/groups/assign", response_model=BulkActionResult)
async def assign_records(
    request: GroupAssignRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Move records into ``group_id`` (or out of any folder with ``null``)."""
    if not request.record_ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")

    if request.group_id is not None:
        _get_group_or_404(db, request.group_id)

    records = (
        db.query(ImageRecord).filter(ImageRecord.id.in_(request.record_ids)).all()
    )
    found_ids = {record.id for record in records}
    for record in records:
        record.group_id = request.group_id
    db.commit()

    return BulkActionResult(
        updated=len(records),
        missing=[rid for rid in request.record_ids if rid not in found_ids],
    )
