"""Gallery file access - preview and download of the *current* image.

The legacy ``/api/records/{id}/download`` only serves READY (upload-staged)
files, which is right for Adobe delivery but wrong for the gallery: an operator
looking at a mid-pipeline cut-out wants that file now. This router serves the
record's current working image (falling back to the untouched original) with
the correct media type, plus a ZIP over the same files for multi-selection.

Endpoints:
* ``GET  /api/records/{id}/file``         - serve inline (viewer) or ``?download=1``
* ``POST /api/records/file-zip``          - ZIP many current files
"""

from __future__ import annotations

import logging
import mimetypes
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from config import ADOBE_STOCK_ROOT, settings
from database import get_db
from models import ImageRecord
from schemas import DeleteRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gallery-files"])

#: Cap the archive so a runaway selection cannot pin the event loop for minutes.
MAX_ZIP_FILES = 200


def _get_record_or_404(db: Session, record_id: str) -> ImageRecord:
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")
    return record


def current_file(record: ImageRecord) -> Path | None:
    """The image to show right now: the working copy, else the original.

    ``working_path`` tracks the pipeline's latest output (a background-removed
    PNG, an upscaled JPEG); the original is the fallback for records no step
    has touched yet.
    """
    for candidate in (record.working_path, record.original_path):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def media_type_for(path: Path) -> str:
    """Guess from the suffix - PNG cut-outs must not be served as ``image/jpeg``."""
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def download_filename(record: ImageRecord, path: Path) -> str:
    """Operator's delivery name when set, else the file we are actually serving."""
    if record.download_name:
        return record.download_name
    return path.name


@router.get("/api/records/{record_id}/file")
async def serve_current_file(
    record_id: str,
    download: bool = Query(
        default=False,
        description="Attachment (download) instead of inline (viewer).",
    ),
    db: Session = Depends(get_db),
):
    """Serve the record's current image for the viewer or a direct download."""
    record = _get_record_or_404(db, record_id)
    path = current_file(record)
    if path is None:
        raise HTTPException(
            status_code=404,
            detail="No image file is available for this record yet.",
        )

    headers = {"Cache-Control": "private, max-age=5"}
    if download:
        # ASCII fallback plus RFC 5987 UTF-8 form, so non-ASCII titles survive.
        name = download_filename(record, path)
        headers["Content-Disposition"] = (
            f"attachment; filename=\"{name.encode('ascii', 'ignore').decode() or path.name}\"; "
            f"filename*=UTF-8''{_url_quote(name)}"
        )
    return FileResponse(
        path=str(path),
        media_type=media_type_for(path),
        headers=headers,
    )


def _url_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


@router.post("/api/records/file-zip")
async def zip_current_files(
    request: DeleteRequest,
    db: Session = Depends(get_db),
):
    """Stream a ZIP of the selected records' current images."""
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
        suffix=".zip", delete=False, dir=str(ADOBE_STOCK_ROOT)
    )
    tmp.close()
    zip_path = Path(tmp.name)

    used: set[str] = set()
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for record in records:
                path = current_file(record)
                if path is None:
                    logger.warning("Skipping record %s: no current file", record.id)
                    continue
                name = download_filename(record, path)
                if name in used:
                    stem = Path(name).stem[:40] or record.id[:8]
                    name = f"{stem}-{record.id[:8]}{path.suffix.lower()}"
                used.add(name)
                archive.write(path, arcname=name)
    except Exception:
        zip_path.unlink(missing_ok=True)
        logger.exception("Failed to build gallery ZIP")
        raise HTTPException(status_code=500, detail="Failed to build the ZIP archive.")

    if not used:
        zip_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=409,
            detail="None of the selected records have image files to download.",
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename="gallery-images.zip",
        background=BackgroundTask(lambda: zip_path.unlink(missing_ok=True)),
    )
