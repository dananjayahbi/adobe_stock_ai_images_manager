"""Gallery router - usage tracking, deletion, downloads, and upload tables."""

import logging
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from config import STORAGE_ROOT, settings
from database import get_db
from models import ImageRecord, ImageStatus, utcnow
from schemas import (
    BulkActionResult,
    BulkUsedRequest,
    DeleteRequest,
    UploadTableResponse,
    UsedRequest,
)
from services.storage import delete_record_files, resolve_ready_path
from services.upload_table import build_download_name, build_upload_row

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gallery"])

MAX_BULK_OPERATION = 500
MAX_ZIP_FILES = 50


def _get_record_or_404(db: Session, record_id: str) -> ImageRecord:
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")
    return record


def _resolve_download_path(record: ImageRecord) -> Path:
    """Resolve the staged file for a record, raising a helpful HTTP error."""
    if record.status != ImageStatus.READY:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Record is in {record.status.value} state. Only READY "
                "(upload-ready) assets can be downloaded."
            ),
        )
    path = resolve_ready_path(record, settings.READY_DIR)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="Staged file is missing from the ready_to_upload directory.",
        )
    return path


# --------------------------------------------------------------------------- #
# Usage tracking
# --------------------------------------------------------------------------- #

@router.patch("/api/records/{record_id}/used", response_model=BulkActionResult)
async def set_record_used(
    record_id: str,
    request: UsedRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Mark a single record as used or unused."""
    record = _get_record_or_404(db, record_id)
    record.is_used = bool(request.is_used)
    record.used_at = utcnow() if request.is_used else None
    db.commit()
    return BulkActionResult(updated=1)


@router.patch("/api/records/used", response_model=BulkActionResult)
async def set_records_used(
    request: BulkUsedRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Mark many records as used or unused in a single transaction."""
    if not request.record_ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(request.record_ids) > MAX_BULK_OPERATION:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update more than {MAX_BULK_OPERATION} records at once.",
        )

    records = (
        db.query(ImageRecord)
        .filter(ImageRecord.id.in_(request.record_ids))
        .all()
    )
    found_ids = {record.id for record in records}
    timestamp = utcnow()

    for record in records:
        record.is_used = bool(request.is_used)
        record.used_at = timestamp if request.is_used else None

    db.commit()

    return BulkActionResult(
        updated=len(records),
        missing=[rid for rid in request.record_ids if rid not in found_ids],
    )


# --------------------------------------------------------------------------- #
# Deletion
# --------------------------------------------------------------------------- #

@router.delete("/api/records/{record_id}", response_model=BulkActionResult)
async def delete_record(record_id: str, db: Session = Depends(get_db)) -> BulkActionResult:
    """Delete a record and every on-disk artifact it owns."""
    record = _get_record_or_404(db, record_id)
    delete_record_files(record, settings)
    db.delete(record)
    db.commit()
    return BulkActionResult(deleted=1)


@router.post("/api/records/bulk-delete", response_model=BulkActionResult)
async def bulk_delete_records(
    request: DeleteRequest,
    db: Session = Depends(get_db),
) -> BulkActionResult:
    """Delete many records plus their files, reporting per-record failures."""
    if not request.record_ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(request.record_ids) > MAX_BULK_OPERATION:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete more than {MAX_BULK_OPERATION} records at once.",
        )

    records = (
        db.query(ImageRecord)
        .filter(ImageRecord.id.in_(request.record_ids))
        .all()
    )
    found_ids = {record.id for record in records}
    deleted = 0

    for record in records:
        delete_record_files(record, settings)
        db.delete(record)
        deleted += 1

    db.commit()

    return BulkActionResult(
        deleted=deleted,
        missing=[rid for rid in request.record_ids if rid not in found_ids],
    )


# --------------------------------------------------------------------------- #
# Downloads
# --------------------------------------------------------------------------- #

@router.get("/api/records/{record_id}/download")
async def download_record(record_id: str, db: Session = Depends(get_db)):
    """Download the staged, metadata-tagged file for a READY record."""
    record = _get_record_or_404(db, record_id)
    path = _resolve_download_path(record)
    return FileResponse(
        path=str(path),
        media_type="image/jpeg",
        filename=build_download_name(record, path, disambiguator=record.id),
    )


@router.post("/api/records/download-zip")
async def download_records_zip(request: DeleteRequest, db: Session = Depends(get_db)):
    """Stream a ZIP archive containing the staged files for many records."""
    if not request.record_ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(request.record_ids) > MAX_ZIP_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot archive more than {MAX_ZIP_FILES} files at once.",
        )

    records = (
        db.query(ImageRecord)
        .filter(ImageRecord.id.in_(request.record_ids))
        .order_by(ImageRecord.created_at.desc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="No matching records found.")

    tmp = tempfile.NamedTemporaryFile(
        suffix=".zip", delete=False, dir=str(STORAGE_ROOT)
    )
    tmp.close()
    zip_path = Path(tmp.name)

    used_names: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for record in records:
                path = resolve_ready_path(record, settings.READY_DIR)
                if path is None:
                    logger.warning("Skipping unstaged record %s in ZIP", record.id)
                    continue
                # The disambiguator keeps two long, similarly-titled assets from
                # collapsing to the same 30-character name. The set below is a
                # belt-and-braces guard in case two ids ever slugify identically.
                name = build_download_name(record, path, disambiguator=record.id)
                if name in used_names:
                    stem_budget = max(len(name) - len(path.suffix) - 9, 1)
                    name = f"{name[:stem_budget]}-{record.id[:8]}{path.suffix.lower()}"
                used_names.add(name)
                archive.write(path, arcname=name)
    except Exception:
        zip_path.unlink(missing_ok=True)
        logger.exception("Failed to build ZIP archive")
        raise HTTPException(status_code=500, detail="Failed to build the ZIP archive.")

    if not used_names:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail="None of the selected records have staged files to download.",
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename="adobe-stock-upload-batch.zip",
        background=BackgroundTask(lambda: zip_path.unlink(missing_ok=True)),
    )


# --------------------------------------------------------------------------- #
# Upload table
# --------------------------------------------------------------------------- #

@router.post("/api/upload-table", response_model=UploadTableResponse)
async def build_upload_table(
    request: DeleteRequest,
    http_request: Request,
    db: Session = Depends(get_db),
) -> UploadTableResponse:
    """Return ordered metadata rows for the selected records.

    The frontend renders these in a dedicated tab with copy buttons and image
    previews, so the operator can paste straight into Adobe Stock.
    """
    if not request.record_ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(request.record_ids) > MAX_BULK_OPERATION:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot build a table for more than {MAX_BULK_OPERATION} records.",
        )

    records = (
        db.query(ImageRecord)
        .filter(ImageRecord.id.in_(request.record_ids))
        .all()
    )
    by_id = {record.id: record for record in records}

    base_url = str(http_request.base_url).rstrip("/")
    items = [
        build_upload_row(by_id[rid], base_url, disambiguator=rid)
        for rid in request.record_ids
        if rid in by_id
    ]

    return UploadTableResponse(
        items=items,
        missing=[rid for rid in request.record_ids if rid not in by_id],
    )
