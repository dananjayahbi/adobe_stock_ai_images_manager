"""Upload router - handles multipart image uploads.

The Collector accepts JPEG and PNG. A PNG is normalised to JPEG at quality 100
as part of ingestion, because Adobe Stock refuses PNG for photos while most
generative tools emit it. The uploaded original is kept byte-for-byte in the
inbox; the JPEG becomes the record's working copy.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import (
    ImageLifecycleState,
    ImageRecord,
    ImageStatus,
    PipelineStage,
    generate_uuid,
    utcnow,
)
from schemas import UploadResponse
from services.image_normalizer import convert_png_to_jpeg, needs_conversion
from services.storage import generate_thumbnail, save_uploaded_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["upload"])

MAX_BATCH_SIZE = 50


@router.post("/upload", response_model=UploadResponse)
async def upload_images(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Accept a batch of image uploads and register them at Stage 1.

    Steps: validate batch + extensions -> save to inbox -> normalise PNG to
    JPEG -> generate thumbnails -> create COLLECTED records in a single
    transaction. No auditing runs here; the operator drives Stages 2-7 from the
    pipeline workspace.
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

            # A PNG is unusable for Adobe Stock as-is, so a JPEG copy is written
            # now and becomes the working file. The inbox original is untouched.
            # The id is generated up front because the conversion output is named
            # after it; the column default would not be applied until flush.
            record_id = generate_uuid()
            working_path = str(full_path)
            stage_detail: dict | None = None
            if needs_conversion(full_path, settings):
                conversion = convert_png_to_jpeg(
                    full_path,
                    settings.CONVERTED_DIR,
                    record_id,
                    quality=settings.PNG_CONVERSION_QUALITY,
                )
                if conversion.converted and conversion.output_path:
                    working_path = conversion.output_path
                    written_files.append(Path(conversion.output_path))
                else:
                    logger.warning(
                        "PNG conversion failed for %s: %s", full_path, conversion.reason
                    )
                stage_detail = {"collector": conversion.to_dict()}

            thumb_path = generate_thumbnail(
                working_path, settings.THUMBNAILS_DIR, Path(full_path).stem
            )
            if thumb_path:
                written_files.append(Path(thumb_path))

            record = ImageRecord(
                id=record_id,
                filename=upload.filename or Path(full_path).name,
                original_path=str(full_path),
                thumbnail_path=thumb_path or None,
                status=ImageStatus.PENDING,
                # New uploads enter the stage workspace at Stage 1 (Collector).
                stage=PipelineStage.COLLECTED,
                # ...and the lifecycle at "not processed yet".
                state=ImageLifecycleState.COLLECTED,
                working_path=working_path,
                stage_updated_at=utcnow(),
                stage_details=stage_detail,
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

    # Stage 1 is collection only. The operator explicitly triggers OCR (Stage 2)
    # and every later stage from the workspace, so no audit runs on upload.

    return UploadResponse(
        record_ids=[record.id for record in created_records],
        count=len(created_records),
    )
