"""Step profiles router - saved, reusable step recipes (batch pipeline v2).

A profile is a named ``steps`` list (with configs) for one media type. The
New Batch modal offers profiles right after the media-type choice; picking one
seeds the batch, and the processing page shows those settings already filled in.

Profiles are deliberately separate from batches: a profile is intent ("how I
always process cut-outs"), a batch is one execution of it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from models import StepProfile, generate_uuid, utcnow
from services import pipeline_defs

router = APIRouter(tags=["step-profiles"])


class ProfileCreateRequest(BaseModel):
    name: str
    media_type: str = "raster"
    steps: list[dict] = Field(default_factory=list)


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    steps: list[dict] | None = None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    media_type: str
    steps: list[dict]
    created_at: datetime
    updated_at: datetime


class ProfileListResponse(BaseModel):
    items: list[ProfileResponse]
    total: int


def _validate_media_type(media_type: str) -> str:
    if media_type not in ("raster", "png"):
        raise HTTPException(status_code=400, detail="media_type must be 'raster' or 'png'.")
    return media_type


def _normalise(steps: list, media_type: str) -> list[dict]:
    try:
        return pipeline_defs.normalise_steps(steps, media_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _get_or_404(db: Session, profile_id: str) -> StepProfile:
    profile = db.get(StepProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Step profile not found.")
    return profile


@router.get("/api/step-profiles", response_model=ProfileListResponse)
async def list_profiles(
    media_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ProfileListResponse:
    """Profiles, optionally filtered to one media type, newest first."""
    query = db.query(StepProfile)
    if media_type is not None:
        _validate_media_type(media_type)
        query = query.filter(StepProfile.media_type == media_type)
    profiles = query.order_by(StepProfile.created_at.desc()).all()
    return ProfileListResponse(
        items=[ProfileResponse.model_validate(p) for p in profiles],
        total=len(profiles),
    )


@router.post("/api/step-profiles", response_model=ProfileResponse, status_code=201)
async def create_profile(
    request: ProfileCreateRequest, db: Session = Depends(get_db)
) -> ProfileResponse:
    """Save a named step recipe. Steps are validated like a batch's."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A profile needs a name.")
    media_type = _validate_media_type(request.media_type)
    steps = _normalise(request.steps, media_type)

    profile = StepProfile(
        id=generate_uuid(),
        name=name,
        media_type=media_type,
        steps=steps,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.patch("/api/step-profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: str, request: ProfileUpdateRequest, db: Session = Depends(get_db)
) -> ProfileResponse:
    """Rename a profile or replace its steps."""
    profile = _get_or_404(db, profile_id)
    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="A profile needs a name.")
        profile.name = name
    if request.steps is not None:
        profile.steps = _normalise(request.steps, profile.media_type)
    db.commit()
    db.refresh(profile)
    return ProfileResponse.model_validate(profile)


@router.delete("/api/step-profiles/{profile_id}")
async def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    """Delete a profile. Batches already seeded from it are unaffected."""
    profile = _get_or_404(db, profile_id)
    db.delete(profile)
    db.commit()
    return {"deleted": profile_id}
