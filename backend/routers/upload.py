"""Upload router - handles multipart image uploads."""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import ImageRecord, ImageStatus
from schemas import UploadResponse
from services.storage import generate_thumbnail, save_uploaded_file
from tasks.audit_orchestrator import process_pending_records

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

MAX_BATCH_SIZE = 50


@router.post("/upload", response_model=UploadResponse)
async def upload_images(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Accept a batch of image uploads, persist them, and dispatch background auditing.

    Steps: validate batch + extensions -> save to inbox -> generate thumbnails ->
    create PENDING records in a single transaction -> schedule audit task.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    if len(files) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds the maximum of {MAX_BATCH_SIZE} files.",
        )

    # Validate extensions before any disk writes.
    invalid = [
        f.filename
        for f in files
        if Path(f.filename or "").suffix.lower() not in settings.ALLOWED_EXTENSIONS
    ]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=(
                "Disallowed file extensions for: "
                f"{', '.join(str(name) for name in invalid)}. "
                f"Allowed: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}."
            ),
        )

    created_records: list[ImageRecord] = []
    written_files: list[Path] = []

    try:
        for upload in files:
            _, full_path = await save_uploaded_file(upload, settings.INBOX_DIR)
            written_files.append(Path(full_path))

            file_size = Path(full_path).stat().st_size
            width: int | None = None
            height: int | None = None
            megapixels: float | None = None
            try:
                with Image.open(full_path) as img:
                    width, height = img.size
                    megapixels = round((width * height) / 1_000_000, 2)
            except Exception:
                logger.warning("Could not read dimensions for %s", full_path)

            thumb_path = generate_thumbnail(full_path, settings.THUMBNAILS_DIR, Path(full_path).stem)
            if thumb_path:
                written_files.append(Path(thumb_path))

            record = ImageRecord(
                filename=upload.filename or Path(full_path).name,
                original_path=str(full_path),
                thumbnail_path=thumb_path or None,
                status=ImageStatus.PENDING,
                width=width,
                height=height,
                megapixels=megapixels,
                file_size_bytes=file_size,
            )
            db.add(record)
            created_records.append(record)

        db.commit()
    except Exception:
        db.rollback()
        for path in written_files:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to clean up orphaned file %s", path)
        logger.exception("Upload failed while persisting batch")
        raise HTTPException(status_code=500, detail="Failed to persist uploaded files.")

    for record in created_records:
        db.refresh(record)

    # Schedule the automated audit pipeline outside the request/response cycle.
    background_tasks.add_task(process_pending_records, SessionLocal, settings)

    return UploadResponse(
        record_ids=[record.id for record in created_records],
        count=len(created_records),
    )
