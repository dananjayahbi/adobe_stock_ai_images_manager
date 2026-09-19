"""Stages router - the API surface for the seven-stage pipeline workspace.

Endpoints are grouped by concern:

* ``GET  /api/stages``                 - the static stage registry
* ``GET  /api/stages/summary``         - per-stage record counts
* ``POST /api/stages/{key}/run``       - kick off a batch stage operation
* ``GET  /api/jobs/{job_id}``          - poll batch progress
* ``POST /api/jobs/{job_id}/cancel``   - request cooperative cancellation
* ``GET  /api/records/{id}/preview``   - serve the current working image
* ``PATCH /api/records/{id}/metadata`` - manual Stage 6 metadata edit
* ``POST /api/metadata/csv``           - build/download the Adobe Stock CSV
* ``GET  /api/categories``             - Adobe category code list
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal, get_db
from models import ImageRecord, ImageStatus, PipelineStage, utcnow
from schemas import (
    CategoryResponse,
    CsvExportRequest,
    JobResponse,
    MetadataUpdateRequest,
    RecordResponse,
    StageDefinitionResponse,
    StageRunRequest,
    StageSummaryResponse,
)
from services import csv_export
from services.adobe_categories import all_categories, resolve_category
from services.jobs import STATUS_RUNNING, JobItem, registry
from services.stage_registry import (
    STAGE_BY_VALUE,
    TERMINAL_STAGES,
    serialize_registry,
    stage_name,
    stage_number,
)
from tasks import stage_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stages"])

#: Maximum records accepted by one batch stage run.
MAX_BATCH_SIZE = 500

#: Maps a stage key to the orchestrator callable that advances it.
STAGE_RUNNERS = {
    "ocr": stage_orchestrator.run_ocr_stage,
    "upscale": stage_orchestrator.run_upscale_stage,
    "refine": stage_orchestrator.run_refine_stage,
    "compatibility": stage_orchestrator.run_compatibility_stage,
    "metadata": stage_orchestrator.run_metadata_stage,
    "gallery": stage_orchestrator.publish_records,
}

#: Stages whose runners accept the optional semantic/delay keyword arguments.
STAGES_WITH_OPTIONS = {"refine", "compatibility", "metadata"}


def _get_record_or_404(db: Session, record_id: str) -> ImageRecord:
    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")
    return record


def _validate_ids(record_ids: list[str]) -> list[str]:
    """De-duplicate ids while preserving order and enforcing the batch cap."""
    unique = list(dict.fromkeys(record_ids))
    if not unique:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(unique) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process more than {MAX_BATCH_SIZE} records at once.",
        )
    return unique


# --------------------------------------------------------------------------- #
# Registry and summary
# --------------------------------------------------------------------------- #

@router.get("/api/stages", response_model=list[StageDefinitionResponse])
async def list_stages() -> list[StageDefinitionResponse]:
    """Return the static stage registry (numbers, names, descriptions)."""
    return [StageDefinitionResponse(**item) for item in serialize_registry()]


@router.get("/api/categories", response_model=list[CategoryResponse])
async def list_categories() -> list[CategoryResponse]:
    """Return Adobe Stock's numeric category codes for the CSV column."""
    return [CategoryResponse(**item) for item in all_categories()]


@router.get("/api/stages/summary", response_model=StageSummaryResponse)
async def stage_summary(db: Session = Depends(get_db)) -> StageSummaryResponse:
    """Count records per stage, plus the headline pipeline metrics."""
    rows = (
        db.query(ImageRecord.stage, func.count(ImageRecord.id))
        .group_by(ImageRecord.stage)
        .all()
    )
    counts_by_stage: dict[str, int] = {}
    for stage_value, count in rows:
        # SQLite stores the enum's *name*; normalise in case of legacy rows.
        key = stage_value.value if isinstance(stage_value, PipelineStage) else str(stage_value)
        counts_by_stage[key] = counts_by_stage.get(key, 0) + count

    counts = [
        {
            "stage": stage,
            "number": stage_number(stage),
            "name": stage_name(stage),
            "count": counts_by_stage.get(stage.value, 0),
        }
        for stage in PipelineStage
    ]

    average_score = (
        db.query(func.avg(ImageRecord.acceptance_score))
        .filter(ImageRecord.acceptance_score.isnot(None))
        .scalar()
    )

    return StageSummaryResponse(
        counts=counts,
        total=sum(counts_by_stage.values()),
        ready=counts_by_stage.get(PipelineStage.PUBLISHED.value, 0),
        rejected=counts_by_stage.get(PipelineStage.OCR_REJECTED.value, 0),
        incompatible=counts_by_stage.get(PipelineStage.INCOMPATIBLE.value, 0),
        average_score=round(float(average_score), 4) if average_score else None,
    )


# --------------------------------------------------------------------------- #
# Batch stage execution
# --------------------------------------------------------------------------- #

@router.post("/api/stages/{stage_key}/run", response_model=JobResponse)
async def run_stage(
    stage_key: str,
    request: StageRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> JobResponse:
    """Start a batch stage operation and return the job handle immediately.

    The batch itself runs as a background task so the HTTP response is not held
    open for minutes; the caller polls ``/api/jobs/{id}`` for progress.
    """
    runner = STAGE_RUNNERS.get(stage_key)
    if runner is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown stage '{stage_key}'. "
                f"Valid keys: {', '.join(sorted(STAGE_RUNNERS))}."
            ),
        )

    record_ids = _validate_ids(request.record_ids)

    records = (
        db.query(ImageRecord).filter(ImageRecord.id.in_(record_ids)).all()
    )
    by_id = {record.id: record for record in records}
    # Preserve the caller's ordering; the job report reads best in request order.
    ordered = [by_id[rid] for rid in record_ids if rid in by_id]
    missing = [rid for rid in record_ids if rid not in by_id]
    if not ordered:
        raise HTTPException(status_code=404, detail="None of the given records exist.")

    # Validate the stage's preconditions up front so the operator gets an
    # immediate error instead of a job that fails every item.
    _assert_stage_preconditions(stage_key, db, [record.id for record in ordered])

    # Register the job *before* dispatch so the response can carry a real id
    # the client can poll immediately, with filenames already populated.
    job = registry.create(
        stage_key,
        f"{stage_key}-run",
        [
            JobItem(record_id=record.id, filename=record.filename)
            for record in ordered
        ],
    )
    if missing:
        job.message = f"{len(missing)} record(s) were not found and were skipped."

    kwargs: dict = {"job_id": job.id}
    if stage_key in STAGES_WITH_OPTIONS:
        kwargs["use_semantic"] = request.use_semantic
    if stage_key == "metadata":
        kwargs["delay_seconds"] = request.delay_seconds

    background_tasks.add_task(
        runner, SessionLocal, [record.id for record in ordered], settings, **kwargs
    )

    return JobResponse(**job.to_dict())


def _assert_stage_preconditions(stage_key: str, db: Session, record_ids: list[str]) -> None:
    """Reject a batch whose records are all in the wrong starting stage."""
    if stage_key == "gallery":
        eligible = (
            db.query(func.count(ImageRecord.id))
            .filter(
                ImageRecord.id.in_(record_ids),
                ImageRecord.stage == PipelineStage.METADATA_READY,
            )
            .scalar()
        )
        if not eligible:
            raise HTTPException(
                status_code=409,
                detail="Stage 6 (metadata) must complete before an image can be published.",
            )

    if stage_key in ("refine", "compatibility"):
        blocked = (
            db.query(func.count(ImageRecord.id))
            .filter(
                ImageRecord.id.in_(record_ids),
                ImageRecord.stage.in_(list(TERMINAL_STAGES)),
            )
            .scalar()
        )
        if blocked == len(record_ids):
            raise HTTPException(
                status_code=409,
                detail="Every selected image is already in a terminal stage.",
            )


@router.get("/api/jobs", response_model=list[JobResponse])
async def list_jobs(limit: int = Query(default=10, ge=1, le=50)) -> list[JobResponse]:
    """Return the most recent batch jobs, newest first."""
    return [JobResponse(**job.to_dict(include_items=False)) for job in registry.list_recent(limit)]


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Poll a batch job's progress and per-record results."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Job not found. Jobs are kept in memory only; a server restart "
                "clears them."
            ),
        )
    return JobResponse(**job.to_dict())


@router.post("/api/jobs/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str) -> JobResponse:
    """Request cooperative cancellation; the batch stops between records."""
    job = registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.status != STATUS_RUNNING:
        raise HTTPException(
            status_code=409, detail=f"Job is already {job.status}."
        )
    registry.cancel(job_id)
    return JobResponse(**job.to_dict())


# --------------------------------------------------------------------------- #
# Working-image preview
# --------------------------------------------------------------------------- #

@router.get("/api/records/{record_id}/preview")
async def preview_working_image(
    record_id: str,
    variant: str = Query(
        default="working",
        description="'working' (current pipeline file), 'original', or 'refined'.",
    ),
    db: Session = Depends(get_db),
):
    """Serve the image the pipeline is currently working on.

    The Stage workspace shows before/after comparisons, so the caller can ask
    for the untouched original or the refined copy explicitly.
    """
    record = _get_record_or_404(db, record_id)

    if variant == "original":
        candidate = Path(record.original_path) if record.original_path else None
    elif variant == "refined":
        candidate = settings.REFINED_DIR / f"{record.id}-refined.jpg"
    else:
        candidate = Path(record.working_path or record.original_path or "")

    if not candidate or not candidate.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"No '{variant}' image is available for this record yet.",
        )

    # A short cache window keeps the browser from refetching on every poll
    # while still picking up a freshly refined file within seconds.
    return FileResponse(
        path=str(candidate),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=5"},
    )


# --------------------------------------------------------------------------- #
# Manual metadata editing
# --------------------------------------------------------------------------- #

@router.patch("/api/records/{record_id}/metadata", response_model=RecordResponse)
async def update_metadata(
    record_id: str,
    request: MetadataUpdateRequest,
    db: Session = Depends(get_db),
) -> RecordResponse:
    """Apply a manual metadata edit (Stage 6).

    Every field is optional; only the supplied ones change, so the UI can save
    a single edited keyword without resending the whole row.
    """
    record = _get_record_or_404(db, record_id)

    if request.title is not None:
        record.generated_title = request.title.strip()[:500] or None

    if request.description is not None:
        record.generated_description = request.description.strip() or None

    if request.keywords is not None:
        # Normalise like the CSV exporter does, so a comma inside a keyword
        # cannot silently split it into two on export.
        cleaned: list[str] = []
        seen: set[str] = set()
        for keyword in request.keywords:
            normalised = " ".join(
                str(keyword).replace(",", " ").replace(";", " ").split()
            )
            if not normalised:
                continue
            lowered = normalised.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            cleaned.append(normalised)
        record.generated_keywords = cleaned[:49]

    if request.category is not None:
        record.category = resolve_category(request.category, settings.DEFAULT_ADOBE_CATEGORY)

    # An edit implies the operator considers the metadata final.
    if record.stage == PipelineStage.COMPATIBLE:
        record.stage = PipelineStage.METADATA_READY
        record.stage_updated_at = utcnow()

    db.commit()
    db.refresh(record)
    return RecordResponse.model_validate(record)


# --------------------------------------------------------------------------- #
# CSV export
# --------------------------------------------------------------------------- #

@router.post("/api/metadata/csv")
async def export_csv(request: CsvExportRequest, db: Session = Depends(get_db)) -> Response:
    """Build and return the Adobe Stock CSV for the selected records.

    The CSV is returned as a downloadable attachment; the frontend also offers
    a clipboard copy of the same content for spot checks.
    """
    if request.record_ids is not None and len(request.record_ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export more than {MAX_BATCH_SIZE} rows at once.",
        )

    result = stage_orchestrator.build_metadata_csv(
        SessionLocal, request.record_ids, only_ready=True
    )

    if result.row_count == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "No exportable rows. Generate metadata (Stage 6) for at least one "
                "image before exporting."
            ),
        )

    headers = {
        "Content-Disposition": f'attachment; filename="{csv_export.build_csv_filename()}"',
        # Surface truncation/skip notes without a second round trip.
        "X-Csv-Row-Count": str(result.row_count),
        "X-Csv-Warning-Count": str(len(result.warnings)),
        "X-Csv-Byte-Size": str(result.byte_size),
        "X-Csv-Row-Limit": str(csv_export.MAX_ROWS),
        "X-Csv-Size-Limit": str(csv_export.MAX_FILE_SIZE_BYTES),
    }
    if result.warnings:
        headers["X-Csv-Warnings"] = "; ".join(result.warnings[:5])

    return Response(
        # UTF-8 with a BOM: Adobe requires UTF-8, and the BOM is what stops
        # Excel from mangling accented keywords on the operator's machine.
        content=csv_export.encode_csv_bytes(result.csv_text),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.post("/api/metadata/csv/preview")
async def preview_csv(
    request: CsvExportRequest, db: Session = Depends(get_db)
) -> dict:
    """Return the CSV text plus warnings without triggering a download.

    The Stage 6 panel renders this inline so the operator can sanity-check rows
    before uploading the file to Adobe.
    """
    result = stage_orchestrator.build_metadata_csv(
        SessionLocal, request.record_ids, only_ready=True
    )
    return {
        "csv_text": result.csv_text,
        "row_count": result.row_count,
        "skipped": result.skipped,
        "warnings": result.warnings,
    }


# --------------------------------------------------------------------------- #
# Stage reset
# --------------------------------------------------------------------------- #

@router.post("/api/records/{record_id}/reset-stage", response_model=RecordResponse)
async def reset_stage(
    record_id: str,
    db: Session = Depends(get_db),
) -> RecordResponse:
    """Return a record to Stage 1 so it can be reprocessed.

    Useful when the operator changes a threshold or a model and wants a second
    pass over images that were previously rejected. Stage details are preserved
    so the history is not lost.
    """
    record = _get_record_or_404(db, record_id)

    if record.stage == PipelineStage.PUBLISHED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Published assets cannot be reset; the staged file already carries "
                "embedded metadata. Delete and re-upload instead."
            ),
        )

    record.stage = PipelineStage.COLLECTED
    record.stage_updated_at = utcnow()
    record.status = ImageStatus.PENDING
    record.acceptance_score = None
    record.acceptance_report = None
    record.refine_passes = 0
    record.working_path = None

    db.commit()
    db.refresh(record)
    return RecordResponse.model_validate(record)
