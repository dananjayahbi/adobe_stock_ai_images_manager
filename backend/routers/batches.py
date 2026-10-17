"""Batches router - the API surface for batch pipeline v2.

Endpoints are grouped by concern:

* ``GET    /api/batches/steps``     - the step catalog (per media type)
* ``GET    /api/batches``           - list batches, newest first
* ``POST   /api/batches``           - create a draft batch
* ``GET    /api/batches/{id}``      - batch + step progress + records
* ``GET    /api/batches/{id}/events`` - SSE stream of BatchResponse frames
* ``PATCH  /api/batches/{id}```     - edit name/steps while not running
* ``DELETE /api/batches/{id}```     - delete a batch (and its records)
* ``POST   /api/batches/{id}/files``  - upload images into the batch
* ``POST   /api/batches/{id}/queue``  - enqueue on the serial worker
* ``POST   /api/batches/{id}/run``    - enqueue (compat alias of /queue)
* ``POST   /api/batches/{id}/cancel`` - cooperative cancel

Batches run one at a time: ``/queue`` (and ``/run``, which now shares its
semantics) stamps ``status='queued'`` and the module-level worker in
``services.batch_queue`` claims rows FIFO.

The legacy stage workspace endpoints are untouched; batches are additive.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import (
    Batch,
    ImageLifecycleState,
    ImageRecord,
    ImageStatus,
    PipelineStage,
    generate_uuid,
    utcnow,
)
from schemas import RecordResponse
from services import batch_queue, pipeline_defs, pipeline_runner, source_folder
from services.image_normalizer import convert_png_to_jpeg, needs_conversion
from services.research.events import SSE_DONE_FRAME, sse_frame
from services.storage import (
    copy_into_inbox,
    delete_record_files,
    generate_thumbnail,
    save_uploaded_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["batches"])

MAX_BATCH_IMAGES = 500
MAX_UPLOAD_FILES = 50

#: Extensions a PNG batch accepts. Same as the photo pipeline - the background
#: remover handles both, and a PNG batch's *output* is PNG either way.
ALLOWED_UPLOADS = settings.ALLOWED_EXTENSIONS


# --------------------------------------------------------------------------- #
# Request / response models
# --------------------------------------------------------------------------- #

class StepEntry(BaseModel):
    """One step in a batch or profile: a catalog key plus its config."""

    key: str
    config: dict = Field(default_factory=dict)


class BatchCreateRequest(BaseModel):
    name: str = ""
    media_type: str = "raster"  # raster | png
    steps: list[StepEntry] = Field(default_factory=list)
    profile_id: str | None = None
    #: Server-side import: relative paths under the configured source folder
    #: (browse via ``/api/fs``). ``None``/omitted keeps the legacy flow of
    #: creating an empty draft and uploading through ``POST .../files``.
    files: list[str] | None = None


class BatchUpdateRequest(BaseModel):
    name: str | None = None
    steps: list[StepEntry] | None = None


class BatchResponse(BaseModel):
    id: str
    name: str
    media_type: str
    steps: list[dict]
    profile_id: str | None = None
    status: str
    #: When the batch entered the serial queue (ISO); null until queued once.
    queued_at: str | None = None
    step_progress: dict | None = None
    error: str | None = None
    record_count: int = 0
    created_at: str
    updated_at: str
    finished_at: str | None = None


class BatchListResponse(BaseModel):
    items: list[BatchResponse]
    total: int


class BatchDetailResponse(BatchResponse):
    records: list[RecordResponse] = []


class UploadResult(BaseModel):
    record_ids: list[str]
    count: int
    errors: list[str] = []


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _batch_response(batch: Batch, record_count: int = 0) -> BatchResponse:
    return BatchResponse(
        id=batch.id,
        name=batch.name,
        media_type=batch.media_type,
        steps=batch.steps or [],
        profile_id=batch.profile_id,
        status=batch.status,
        queued_at=_iso(batch.queued_at),
        step_progress=batch.step_progress,
        error=batch.error,
        record_count=record_count,
        created_at=_iso(batch.created_at) or "",
        updated_at=_iso(batch.updated_at) or "",
        finished_at=_iso(batch.finished_at),
    )


def _get_batch_or_404(db: Session, batch_id: str) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} does not exist.")
    return batch


def _record_count(db: Session, batch_id: str) -> int:
    return (
        db.query(func.count(ImageRecord.id))
        .filter(ImageRecord.batch_id == batch_id)
        .scalar()
        or 0
    )


def _validate_media_type(media_type: str) -> str:
    if media_type not in ("raster", "png"):
        raise HTTPException(
            status_code=400,
            detail="media_type must be 'raster' or 'png'.",
        )
    return media_type


def _normalise_or_400(steps: list, media_type: str) -> list[dict]:
    try:
        return pipeline_defs.normalise_steps(steps, media_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _ingest_inbox_file(
    db: Session,
    batch: Batch,
    full_path: Path,
    display_name: str,
    *,
    written: list[Path],
) -> str:
    """Create the ImageRecord for one file already staged in the inbox.

    The single ingestion path shared by ``POST .../files`` and the
    create-with-``files`` import: dimensions → (raster) PNG-to-JPEG
    conversion → thumbnail → record insert. It does **not** commit — the
    caller owns the transaction — and appends every file it creates to
    ``written`` so the caller's failure path can unlink them all.

    Returns the new record id.
    """
    keep_alpha = batch.media_type == "png"

    file_size = full_path.stat().st_size
    width = height = megapixels = None
    try:
        with Image.open(full_path) as img:
            width, height = img.size
            megapixels = round((width * height) / 1_000_000, 2)
    except Exception:  # noqa: BLE001
        logger.warning("Could not read dimensions for %s", full_path)

    record_id = generate_uuid()
    working_path = str(full_path)
    stage_detail: dict | None = None

    if not keep_alpha and needs_conversion(full_path, settings):
        conversion = convert_png_to_jpeg(
            full_path,
            settings.CONVERTED_DIR,
            record_id,
            quality=settings.PNG_CONVERSION_QUALITY,
        )
        if conversion.converted and conversion.output_path:
            working_path = conversion.output_path
            written.append(Path(conversion.output_path))
        stage_detail = {"collector": conversion.to_dict()}

    # For alpha, the thumbnail keeps its channel: the gallery shows
    # the cut-out over the card's own background (a white JPEG would
    # paint a plate over the dark theme).
    if keep_alpha:
        from services import png_ops

        thumb_path = png_ops.alpha_thumbnail(
            working_path, settings.THUMBNAILS_DIR, full_path.stem
        )
    else:
        thumb_path = generate_thumbnail(
            working_path, settings.THUMBNAILS_DIR, full_path.stem
        )
    if thumb_path:
        written.append(Path(thumb_path))

    record = ImageRecord(
        id=record_id,
        filename=display_name,
        original_path=str(full_path),
        thumbnail_path=thumb_path or None,
        status=ImageStatus.PENDING,
        stage=PipelineStage.COLLECTED,
        state=ImageLifecycleState.COLLECTED,
        batch_id=batch.id,
        working_path=working_path,
        # Deliberately NULL until a pipeline step touches the record:
        # `stage_updated_at IS NOT NULL` is the "processed" signal the
        # new home/gallery use, and an upload alone is not processing.
        stage_updated_at=None,
        stage_details=stage_detail,
        width=width,
        height=height,
        megapixels=megapixels,
        file_size_bytes=file_size,
    )
    db.add(record)
    return record_id


def _resolve_import_paths(rel_paths: list[str]) -> list[tuple[str, Path]]:
    """Validate ``BatchCreateRequest.files`` against the source folder.

    Contract order: containment inside the source root (403 on escape),
    then existence + extension (400, naming the offender), then the batch
    image cap (409). Runs *before* the batch row is created, so any
    rejection leaves nothing behind.
    """
    resolved: list[tuple[str, Path]] = []
    for raw in rel_paths:
        rel = str(raw)
        # 400 when no source folder is configured, 403 on a realpath escape.
        target = source_folder.resolve_inside(rel)
        if not target.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"File not found in the source folder: {rel}",
            )
        if target.suffix.lower() not in ALLOWED_UPLOADS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Disallowed file extension for: {rel}. "
                    f"Allowed: {', '.join(sorted(ALLOWED_UPLOADS))}."
                ),
            )
        resolved.append((rel, target))
    if len(resolved) > MAX_BATCH_IMAGES:
        raise HTTPException(
            status_code=409,
            detail=f"A batch holds at most {MAX_BATCH_IMAGES} images.",
        )
    return resolved


# --------------------------------------------------------------------------- #
# Step catalog
# --------------------------------------------------------------------------- #

@router.get("/api/batches/steps")
async def step_catalog(media_type: str | None = Query(default=None)):
    """The step catalog: keys, labels, descriptions, default configs."""
    if media_type is not None:
        _validate_media_type(media_type)
    return {
        "order": list(pipeline_defs.STEP_ORDER),
        "steps": pipeline_defs.catalog_payload(media_type),
        "media_types": {"raster": available("raster"), "png": available("png")},
    }


def available(media_type: str) -> list[str]:
    return pipeline_defs.available_steps(media_type)


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #

@router.get("/api/batches", response_model=BatchListResponse)
async def list_batches(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> BatchListResponse:
    """Newest-first batch list with image counts (home page + badges)."""
    rows = (
        db.query(ImageRecord.batch_id, func.count(ImageRecord.id))
        .group_by(ImageRecord.batch_id)
        .all()
    )
    counts = {batch_id: count for batch_id, count in rows if batch_id}

    batches = (
        db.query(Batch)
        .order_by(Batch.created_at.desc())
        .limit(limit)
        .all()
    )
    return BatchListResponse(
        items=[_batch_response(b, counts.get(b.id, 0)) for b in batches],
        total=db.query(func.count(Batch.id)).scalar() or 0,
    )


@router.post("/api/batches", response_model=BatchResponse, status_code=201)
async def create_batch(request: BatchCreateRequest, db: Session = Depends(get_db)):
    """Create a draft batch. Steps may be omitted to inherit a profile's.

    When ``files`` is given, each relative path is imported from the
    configured source folder through the same ingestion helper the upload
    endpoint uses (inbox copy → convert → thumbnail → record).
    """
    media_type = _validate_media_type(request.media_type)

    steps = [entry.model_dump() for entry in request.steps]
    profile_id = request.profile_id

    if not steps and profile_id:
        steps = _load_profile_steps(db, profile_id, media_type)

    normalised = _normalise_or_400(steps, media_type)

    # Validate every import path before the batch row exists: a 400/403/409
    # rejection must leave nothing to roll back.
    imports = _resolve_import_paths(request.files) if request.files else []

    batch = Batch(
        id=generate_uuid(),
        name=(request.name or "").strip() or _default_batch_name(media_type),
        media_type=media_type,
        steps=normalised,
        profile_id=profile_id,
        status="draft",
        step_progress=None,
    )
    db.add(batch)

    written: list[Path] = []
    imported: list[str] = []
    if imports:
        try:
            for _, target in imports:
                inbox_path = copy_into_inbox(target, settings.INBOX_DIR)
                written.append(inbox_path)
                imported.append(
                    _ingest_inbox_file(
                        db, batch, inbox_path, target.name, written=written
                    )
                )
            db.commit()
        except Exception:
            db.rollback()
            for path in written:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not clean up %s", path)
            raise

    db.commit()
    db.refresh(batch)
    return _batch_response(batch, len(imported))


def _default_batch_name(media_type: str) -> str:
    label = "PNG objects" if media_type == "png" else "Raster photos"
    return f"{label} · {utcnow().strftime('%Y-%m-%d %H:%M')}"


def _load_profile_steps(db: Session, profile_id: str, media_type: str) -> list:
    from models import StepProfile

    profile = db.get(StepProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Step profile not found.")
    if profile.media_type != media_type:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Profile '{profile.name}' is for {profile.media_type} batches, "
                f"not {media_type}."
            ),
        )
    return list(profile.steps or [])


@router.get("/api/batches/{batch_id}", response_model=BatchDetailResponse)
async def get_batch(batch_id: str, db: Session = Depends(get_db)):
    """One batch with its live step progress and its images."""
    batch = _get_batch_or_404(db, batch_id)
    records = (
        db.query(ImageRecord)
        .filter(ImageRecord.batch_id == batch_id)
        .order_by(ImageRecord.created_at)
        .all()
    )
    detail = BatchDetailResponse(
        **_batch_response(batch, len(records)).model_dump(),
        records=[RecordResponse.model_validate(record) for record in records],
    )
    return detail


# --------------------------------------------------------------------------- #
# Live stream (SSE)
# --------------------------------------------------------------------------- #

#: Once the batch lands in one of these states the stream sends the final
#: frame followed by the done event and closes.
_BATCH_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

#: Seconds between state polls inside the generator: fast enough to feel live,
#: slow enough not to hammer the database.
_BATCH_POLL_SECONDS = 0.5

#: Silence after which a comment ping is due, so an idle proxy (or tunnel)
#: does not close the connection before the batch finishes.
_BATCH_PING_SECONDS = 15.0

#: SSE comment ping - comment lines are consumed by the parser without
#: producing a client-visible event, exactly what a keep-alive needs.
_BATCH_PING_FRAME = ": ping\n\n"

#: Headers that stop a proxy from buffering the SSE stream. Mirrors the set in
#: routers/research.py so every stream in this app behaves the same behind
#: Cloudflare.
_BATCH_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def get_batch_session_factory():
    """Session factory the SSE generator opens its own sessions from.

    A dependency (same pattern as research's ``get_session_factory``): FastAPI
    closes the request-scoped session before a streaming body is consumed, so
    the generator must open its own - and tests can override the dependency to
    point the stream at their database.
    """
    return SessionLocal


def _current_batch_payload(session_factory, batch_id: str) -> BatchResponse | None:
    """One poll of the batch's current state; None once the batch is gone."""
    with session_factory() as session:
        batch = session.get(Batch, batch_id)
        if batch is None:
            return None
        return _batch_response(batch, _record_count(session, batch_id))


@router.get("/api/batches/{batch_id}/events")
async def stream_batch_events(
    batch_id: str,
    db: Session = Depends(get_db),
    session_factory=Depends(get_batch_session_factory),
) -> StreamingResponse:
    """Stream BatchResponse frames while the batch progresses (mobile SSE).

    The frames carry the exact ``BatchResponse`` JSON that
    ``GET /api/batches/{id}`` serves (without the record list), so a client
    parses one model for polling and streaming alike: an immediate snapshot,
    then a frame whenever status/step_progress changes, then the
    research-style ``event: done`` marker once the batch reaches a terminal
    state. Idle stretches get a comment ping every 15 seconds so proxies do
    not time the connection out.
    """
    # Probe while the request session is still open, so an unknown id is a
    # normal 404 instead of a stream that opens and never produces a frame.
    _get_batch_or_404(db, batch_id)

    async def generate() -> AsyncIterator[str]:
        last_frame: str | None = None
        last_ping = time.monotonic()
        while True:
            payload = _current_batch_payload(session_factory, batch_id)
            if payload is None:
                # Deleted mid-stream: no further state will ever appear, so
                # close cleanly rather than pinging an id that cannot move.
                yield SSE_DONE_FRAME
                return
            frame = sse_frame(payload.model_dump())
            if frame != last_frame:
                yield frame
                last_frame = frame
                last_ping = time.monotonic()
            if payload.status in _BATCH_TERMINAL_STATUSES:
                yield SSE_DONE_FRAME
                return
            if time.monotonic() - last_ping >= _BATCH_PING_SECONDS:
                yield _BATCH_PING_FRAME
                last_ping = time.monotonic()
            await asyncio.sleep(_BATCH_POLL_SECONDS)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=_BATCH_SSE_HEADERS,
    )


@router.patch("/api/batches/{batch_id}", response_model=BatchResponse)
async def update_batch(
    batch_id: str, request: BatchUpdateRequest, db: Session = Depends(get_db)
):
    """Edit the name or steps of a batch that is not currently running."""
    batch = _get_batch_or_404(db, batch_id)
    if batch.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Cannot edit a batch while it is running.",
        )
    if request.name is not None:
        batch.name = request.name.strip() or batch.name
    if request.steps is not None:
        batch.steps = _normalise_or_400(
            [entry.model_dump() for entry in request.steps], batch.media_type
        )
    # The steps changed, so previous per-step results no longer describe them.
    batch.step_progress = None
    batch.error = None
    if batch.status in ("completed", "failed", "cancelled"):
        batch.status = "draft"
        batch.finished_at = None
    db.commit()
    db.refresh(batch)
    return _batch_response(batch, _record_count(db, batch.id))


@router.delete("/api/batches/{batch_id}")
async def delete_batch(batch_id: str, db: Session = Depends(get_db)):
    """Delete a batch and the images uploaded into it (files included)."""
    batch = _get_batch_or_404(db, batch_id)
    if batch.status == "running":
        raise HTTPException(
            status_code=409,
            detail="Cancel the batch before deleting it.",
        )

    records = (
        db.query(ImageRecord).filter(ImageRecord.batch_id == batch_id).all()
    )
    for record in records:
        delete_record_files(record, settings)
        db.delete(record)
    db.delete(batch)
    db.commit()
    return {"deleted": batch_id, "images": len(records)}


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #

@router.post("/api/batches/{batch_id}/files", response_model=UploadResult)
async def upload_to_batch(
    batch_id: str,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadResult:
    """Upload images into a draft batch.

    A **raster** batch normalises PNGs to JPEG exactly like the Collector does
    (Adobe refuses PNG photos). A **png** batch keeps the alpha channel: the
    uploaded file *is* the working copy, because flattening it would destroy the
    very thing the background remover is about to produce.
    """
    batch = _get_batch_or_404(db, batch_id)
    if batch.status == "running":
        raise HTTPException(status_code=409, detail="Cannot upload while running.")
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"At most {MAX_UPLOAD_FILES} files per upload.",
        )

    existing = _record_count(db, batch_id)
    if existing + len(files) > MAX_BATCH_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"A batch holds at most {MAX_BATCH_IMAGES} images.",
        )

    invalid = [
        f.filename
        for f in files
        if Path(f.filename or "").suffix.lower() not in ALLOWED_UPLOADS
    ]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Disallowed file extensions for: {', '.join(str(n) for n in invalid)}. "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOADS))}."
            ),
        )

    result = UploadResult(record_ids=[], count=0, errors=[])
    written: list[Path] = []

    try:
        for upload in files:
            _, full_path = await save_uploaded_file(upload, settings.INBOX_DIR)
            written.append(Path(full_path))
            # Shared with the create-with-``files`` import: conversion,
            # thumbnail, and the record insert all happen in one place.
            record_id = _ingest_inbox_file(
                db,
                batch,
                Path(full_path),
                upload.filename or Path(full_path).name,
                written=written,
            )
            result.record_ids.append(record_id)
            result.count += 1

        db.commit()
    except Exception:
        db.rollback()
        for path in written:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not clean up %s", path)
        raise

    # Touching the batch moves `updated_at`, which the UI uses for ordering.
    batch.updated_at = utcnow()
    db.commit()
    return result


# --------------------------------------------------------------------------- #
# Queue / run / cancel
# --------------------------------------------------------------------------- #

def _enqueue_precheck(db: Session, batch: Batch) -> int:
    """Shared by /queue and /run: 409 unless the batch may enter the queue.

    Returns the record count the response echoes. The messages stay the ones
    ``/run`` always answered with, so existing clients keep parsing them.
    """
    if batch.status == "running":
        raise HTTPException(status_code=409, detail="This batch is already running.")
    if batch.status == "queued":
        raise HTTPException(status_code=409, detail="This batch is already queued.")
    count = _record_count(db, batch.id)
    if count == 0:
        raise HTTPException(
            status_code=409,
            detail="Upload at least one image before running the batch.",
        )
    if not batch.steps:
        raise HTTPException(status_code=409, detail="This batch has no steps selected.")
    return count


def _enqueue(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session,
    session_factory,
) -> BatchResponse:
    """Move the batch into the serial queue and kick the worker."""
    batch = _get_batch_or_404(db, batch_id)
    count = _enqueue_precheck(db, batch)

    # Reset run-scoped state with the queue entry, so every poll after the
    # response shows the queued batch without stale error/finish markers.
    batch.status = "queued"
    batch.queued_at = utcnow()
    batch.error = None
    batch.finished_at = None
    db.commit()

    # Committed *before* the kick: a worker mid-run claims this row on its
    # next pass; a worker about to exit either sees it in its final claim or
    # the kick that follows schedules a fresh one (atomic with the flag).
    batch_queue.kick(background_tasks, session_factory, settings)

    db.refresh(batch)
    return _batch_response(batch, count)


@router.post("/api/batches/{batch_id}/queue", response_model=BatchResponse)
async def queue_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory=Depends(get_batch_session_factory),
):
    """Enqueue the batch on the serial worker (one batch at a time).

    409 when the batch is already running/queued, has no images, or has no
    steps — the same preconditions ``/run`` answers with.
    """
    return _enqueue(batch_id, background_tasks, db, session_factory)


@router.post("/api/batches/{batch_id}/run", response_model=BatchResponse)
async def run_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory=Depends(get_batch_session_factory),
):
    """Enqueue the whole pipeline (compat path: identical to ``/queue``).

    The path and response shape are unchanged for clients that POST ``/run``
    today, but the effect is enqueue semantics: the response normally reads
    ``status='queued'`` and the serial worker starts it when its turn comes.
    """
    return _enqueue(batch_id, background_tasks, db, session_factory)


@router.post("/api/batches/{batch_id}/cancel", response_model=BatchResponse)
async def cancel_batch(batch_id: str, db: Session = Depends(get_db)):
    """Request cooperative cancellation: between steps, and within the current
    step's per-record loop.

    Also valid from ``queued``: the worker only claims ``status='queued'``
    rows, so the flip alone makes it unclaimable — and if no runner holds the
    batch (the queued case), that flip *is* the whole effect.
    """
    batch = _get_batch_or_404(db, batch_id)
    if batch.status not in ("running", "queued"):
        raise HTTPException(status_code=409, detail="This batch is not running.")

    batch.status = "cancelled"
    batch.finished_at = utcnow()
    db.commit()

    # No-op unless a runner holds the in-flight step job (a queued batch has
    # none); keeping the call keeps the running path byte-for-byte intact.
    pipeline_runner.request_cancel(batch_id)

    db.refresh(batch)
    return _batch_response(batch, _record_count(db, batch_id))
