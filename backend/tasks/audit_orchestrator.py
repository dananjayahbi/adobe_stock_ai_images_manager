"""Background audit orchestrator - processes PENDING records through the QC pipeline."""

import logging
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from config import Settings, settings as default_settings
from models import ImageRecord, ImageStatus
from services import exiftool_embedder, gemini_auditor, gemini_metadata, qc_engine
from services.storage import copy_to_ready

logger = logging.getLogger(__name__)


def _resolve_staging_source(
    record: ImageRecord,
    explicit: Path | str | None,
    cfg: Settings,
) -> Path:
    """The file to stage for upload: the pipeline's best available copy.

    Order of preference:

    1. an explicit ``source_path`` (the caller knows best),
    2. ``working_path`` — the refined/upscaled/JPEG-converted copy that every
       pipeline stage writes to,
    3. the inbox original, only when no working copy exists.

    Staging the original is what made publishing *look* like it compressed the
    image: the staged file matched the raw upload while the 3x-larger quality
    copy sat unused in ``working_path``.
    """
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if record.working_path:
        candidates.append(Path(record.working_path))
    if record.original_path:
        candidates.append(Path(record.original_path))

    for candidate in candidates:
        if candidate.is_file():
            if candidate != Path(record.original_path or ""):
                logger.debug("Staging pipeline copy %s for record %s", candidate, record.id)
            return candidate

    # Nothing exists on disk; return the original so the copy step raises the
    # same clear error it always did rather than failing earlier and obscurely.
    logger.warning(
        "No staged source found for record %s (working_path=%s, original_path=%s)",
        record.id,
        record.working_path,
        record.original_path,
    )
    return Path(record.original_path or "")


def process_pending_records(db_session_factory: Callable[[], Session], settings: Settings | None = None) -> None:
    """Pick up PENDING records and run them through deterministic + semantic QC.

    Designed to be called as a FastAPI BackgroundTasks callable.
    Each invocation creates its own database session to avoid cross-thread issues.

    Args:
        db_session_factory: Callable that returns a new Session (e.g., SessionLocal).
        settings: Optional settings override; uses default_settings if not provided.
    """
    cfg = settings or default_settings
    db: Session = db_session_factory()

    try:
        pending_records = db.query(ImageRecord).filter(
            ImageRecord.status == ImageStatus.PENDING
        ).all()

        if not pending_records:
            logger.debug("No PENDING records to process")
            return

        logger.info("Processing %d PENDING records", len(pending_records))

        for record in pending_records:
            try:
                _process_single_record(record, db, cfg)
            except Exception as e:
                logger.error("Unhandled error processing record %s: %s", record.id, e)
                try:
                    record.status = ImageStatus.FLAGGED
                    db.commit()
                except Exception:
                    db.rollback()
                    logger.error("Failed to flag record %s after unhandled error", record.id)
    finally:
        db.close()


def _process_single_record(record: ImageRecord, db: Session, cfg: Settings) -> None:
    """Process a single record through the full QC pipeline."""
    # Stage 1: Transition to AUDITING
    record.status = ImageStatus.AUDITING
    db.commit()
    logger.info("Record %s transitioned to AUDITING", record.id)

    file_path = Path(record.original_path)

    # Stage 2: Deterministic QC
    qc_result = qc_engine.run_all_checks(file_path, cfg)

    # Persist heuristic results
    checks = qc_result.get("checks", {})
    res_check = checks.get("resolution", {})
    sharp_check = checks.get("sharpness", {})
    ocr_check = checks.get("text_ocr", {})

    record.width = res_check.get("width")
    record.height = res_check.get("height")
    record.megapixels = res_check.get("megapixels")
    record.laplacian_variance = sharp_check.get("laplacian_variance")
    record.ocr_text_detected = ocr_check.get("text_detected", False)
    record.ocr_text_content = ocr_check.get("text_content", "")[:500] if ocr_check.get("text_content") else None

    if not qc_result["passed"]:
        # Persist the deterministic failure reasons so the UI can surface them.
        record.semantic_flags = qc_result.get("reasons", [])
        record.status = ImageStatus.FLAGGED
        db.commit()
        logger.info("Record %s FLAGGED by deterministic QC: %s", record.id, qc_result.get("reasons"))
        return

    db.commit()

    # Stage 3: Semantic Audit via Gemini
    audit_result = gemini_auditor.audit_image(file_path, api_key=cfg.effective_llm_api_key)

    record.semantic_confidence_score = audit_result.get("confidence_score", 0.0)
    record.semantic_flags = audit_result.get("flags", [])

    # Stage 4: Confidence Gate
    if not audit_result["passed"]:
        record.status = ImageStatus.FLAGGED
        db.commit()
        logger.info("Record %s FLAGGED by semantic audit: %s", record.id, audit_result.get("reason"))
        return

    # All checks passed
    record.status = ImageStatus.PASSED
    db.commit()
    logger.info("Record %s PASSED all QC checks", record.id)


def process_approval(
    db_session_factory: Callable[[], Session],
    record_id: str,
    settings: Settings | None = None,
    override_metadata: dict | None = None,
    source_path: Path | str | None = None,
) -> bool:
    """Process an approved record: generate metadata, copy to ready dir, embed EXIF.

    Args:
        db_session_factory: Callable that returns a new Session.
        record_id: The UUID of the record to approve.
        settings: Optional settings override.
        override_metadata: Optional dict with 'title', 'description', 'keywords' to skip generation.
        source_path: The file to stage. Defaults to ``working_path`` - the
            pipeline's current quality copy - and only falls back to the inbox
            original when no working copy exists.

    Returns True on success, False on failure.
    """
    cfg = settings or default_settings
    db: Session = db_session_factory()

    try:
        record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
        if not record:
            logger.error("Record %s not found for approval", record_id)
            return False

        if record.status not in (
            ImageStatus.PASSED,
            ImageStatus.FLAGGED,
            ImageStatus.APPROVED,
        ):
            logger.error(
                "Record %s has status %s, expected PASSED, FLAGGED or APPROVED",
                record_id,
                record.status,
            )
            return False

        # Generate or use override metadata
        if override_metadata:
            metadata = override_metadata
        else:
            metadata = gemini_metadata.generate_metadata(
                record.original_path, api_key=cfg.effective_llm_api_key
            )
            if not metadata:
                logger.error("Metadata generation failed for record %s", record_id)
                return False

        # Store generated metadata on the record
        record.generated_title = metadata.get("title", "")[:500]
        record.generated_description = metadata.get("description", "")
        record.generated_keywords = metadata.get("keywords", [])

        # Stage the pipeline's *quality* copy, never the raw inbox upload.
        #
        # This is the difference between uploading the 4K refined asset and
        # uploading the low-quality file that came out of the generator. Every
        # stage's work lives in `working_path`; publishing the inbox original
        # silently discarded all of it. The original remains the fallback for
        # records that never ran through a stage.
        staged_source = _resolve_staging_source(record, source_path, cfg)

        # Copy file to ready directory
        ready_path_str = copy_to_ready(staged_source, cfg.READY_DIR, record.id)

        if not ready_path_str:
            logger.error("Failed to copy record %s to ready directory", record_id)
            return False

        # Embed metadata into the copied file
        embed_success = exiftool_embedder.embed_metadata(ready_path_str, metadata)
        if not embed_success:
            logger.error("ExifTool embedding failed for record %s; rolling back copy", record_id)
            try:
                Path(ready_path_str).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove staged file %s", ready_path_str)
            db.rollback()
            return False

        # Update status to READY
        record.status = ImageStatus.READY
        db.commit()
        logger.info("Record %s approved and moved to READY status", record_id)
        return True

    except Exception as e:
        db.rollback()
        logger.error("Error during approval of record %s: %s", record_id, e)
        return False
    finally:
        db.close()
