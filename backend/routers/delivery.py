"""Asset-delivery endpoints shared by every stage from Metadata onward.

From Stage 6 onwards the operator's job shifts from *processing* images to
*delivering* them: naming the files, forcing past a gate they disagree with, and
exporting the CSV/ZIP bundle Adobe needs. Those three concerns are the same
wherever the record currently sits, so they live in one router instead of being
duplicated per stage page.

Adobe matches a CSV row to an uploaded image **by filename**, so all of this is
about keeping one name consistent across the CSV, the download and the ZIP.
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from config import STORAGE_ROOT, settings
from database import SessionLocal, get_db
from models import ImageRecord
from schemas import (
    CsvExportRequest,
    ForcedAcceptRequest,
    ForcedAcceptResponse,
    ForcedAcceptResultItem,
    RenameRequest,
    RenameResponse,
    RenameResultItem,
)
from services import asset_naming, csv_export, forced_acceptance
from services.storage import resolve_current_path, resolve_ready_path
from tasks import stage_orchestrator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["delivery"])

#: Most records one delivery call may touch.
MAX_DELIVERY_BATCH = 500

#: Most files in one ZIP, matching the gallery router's own cap.
MAX_ZIP_FILES = 50


def _load_records(db: Session, record_ids: list[str]) -> list[ImageRecord]:
    """Fetch records in the caller's order, de-duplicated."""
    ids = list(dict.fromkeys(record_ids))
    if not ids:
        raise HTTPException(status_code=400, detail="record_ids must not be empty.")
    if len(ids) > MAX_DELIVERY_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process more than {MAX_DELIVERY_BATCH} records at once.",
        )
    records = db.query(ImageRecord).filter(ImageRecord.id.in_(ids)).all()
    by_id = {record.id: record for record in records}
    return [by_id[rid] for rid in ids if rid in by_id]


# --------------------------------------------------------------------------- #
# Naming - what the uploaded file will be called
# --------------------------------------------------------------------------- #

@router.post("/api/assets/rename", response_model=RenameResponse)
async def rename_assets(
    request: RenameRequest,
    db: Session = Depends(get_db),
) -> RenameResponse:
    """Set the upload filename for one or more records.

    Adobe matches a CSV row to an uploaded file by filename, so this is the step
    that makes the CSV trustworthy: the operator fixes the names *before*
    exporting, and the CSV, the download and the ZIP all then agree.

    Names are normalised rather than rejected - the operator types a human name
    and the tool makes it uploadable (slugified, JPEG extension, filename
    cap). Genuine problems (an empty name) are reported per record so one bad
    row cannot fail the whole batch.
    """
    records = _load_records(db, [item.record_id for item in request.items])
    by_id = {record.id: record for record in records}

    items: list[RenameResultItem] = []
    updated = 0
    failed = 0

    for entry in request.items:
        record = by_id.get(entry.record_id)
        if record is None:
            failed += 1
            items.append(
                RenameResultItem(
                    record_id=entry.record_id,
                    filename="",
                    error="Record not found.",
                )
            )
            continue

        if not (entry.name or "").strip():
            # Blank clears the override, returning the record to the derived
            # name. That is a legitimate action, not an error.
            record.download_name = None
            items.append(
                RenameResultItem(
                    record_id=record.id,
                    filename=record.filename,
                    download_name=None,
                    changed=True,
                )
            )
            updated += 1
            continue

        problems = asset_naming.validate_name(entry.name)
        normalised = asset_naming.normalise_name(entry.name)
        # A too-long or oddly-punctuated name is fixable by normalisation, so it
        # is only a hard error when the result would be meaningless.
        hard_problems = [p for p in problems if "empty" in p.lower()]
        if hard_problems:
            failed += 1
            items.append(
                RenameResultItem(
                    record_id=record.id,
                    filename=record.filename,
                    error=" ".join(hard_problems),
                )
            )
            continue

        changed = record.download_name != normalised
        record.download_name = normalised
        updated += 1
        items.append(
            RenameResultItem(
                record_id=record.id,
                filename=record.filename,
                download_name=normalised,
                changed=changed,
            )
        )

    db.commit()

    return RenameResponse(items=items, updated=updated, failed=failed)


@router.post("/api/assets/rename-suggest", response_model=RenameResponse)
async def suggest_names(
    request: RenameRequest,
    db: Session = Depends(get_db),
) -> RenameResponse:
    """Rebuild names from the generated title for the given records.

    This is the "rename them all" action. It is a *suggestion* endpoint: it
    reports what each name would become without writing anything, so the operator
    can review a whole batch before committing. Duplicate names within the batch
    are resolved so the CSV cannot contain two rows for one file.
    """
    ids = [item.record_id for item in request.items]
    records = _load_records(db, ids) if ids else []

    derived = [
        asset_naming.derive_name(record, resolve_ready_path(record, settings.READY_DIR))
        for record in records
    ]
    # De-duplicated as a batch: two records sharing a title would otherwise be
    # offered the same filename, and the CSV cannot carry two rows for one file.
    unique = asset_naming.deduplicate(derived)

    items = [
        RenameResultItem(
            record_id=record.id,
            filename=record.filename,
            download_name=name,
            changed=name != (record.download_name or ""),
        )
        for record, name in zip(records, unique)
    ]
    return RenameResponse(items=items, updated=len(items), failed=0)


@router.post("/api/assets/apply-suggested-names", response_model=RenameResponse)
async def apply_suggested_names(
    request: RenameRequest,
    db: Session = Depends(get_db),
) -> RenameResponse:
    """Adopt the metadata model's proposed filenames for the given records.

    The one-button version of "rename them all". The model named each asset while
    looking at it, so its proposal is usually better than a truncated title —
    but a model's output must never silently become the delivered filename, so
    the proposal is stored separately at generation time and only *this* explicit
    action turns it into the name Adobe will be given.

    A record the model did not name (generated before the model was asked, or an
    answer that normalised to nothing) falls back to its title-derived name, so
    the button is never a no-op on part of a selection.
    """
    ids = [item.record_id for item in request.items]
    records = _load_records(db, ids) if ids else []

    proposed = [
        (record.suggested_filename or "").strip()
        or asset_naming.derive_name(record, resolve_ready_path(record, settings.READY_DIR))
        for record in records
    ]
    # De-duplicated as a batch: the model can propose the same name twice (two
    # similar images), and one CSV cannot carry two rows for one file.
    unique = asset_naming.deduplicate(proposed)

    items: list[RenameResultItem] = []
    applied = 0
    for record, name in zip(records, unique):
        changed = record.download_name != name
        record.download_name = name
        applied += 1
        items.append(
            RenameResultItem(
                record_id=record.id,
                filename=record.filename,
                download_name=name,
                changed=changed,
            )
        )

    db.commit()
    return RenameResponse(items=items, updated=applied, failed=0)


# --------------------------------------------------------------------------- #
# Forced acceptance
# --------------------------------------------------------------------------- #

@router.post("/api/assets/force-accept", response_model=ForcedAcceptResponse)
async def force_accept_records(
    request: ForcedAcceptRequest,
    db: Session = Depends(get_db),
) -> ForcedAcceptResponse:
    """Advance records past the acceptance gate at the operator's discretion.

    The acceptance score is a *ranking* signal, and reviewer variance exceeds any
    threshold's resolution - so there are real cases where the operator knows
    better than the gate. This is the supported path, and it deliberately
    **preserves the measured score and the scorer's issues**: the record still
    shows the honest measurement, and the override is recorded separately in
    ``stage_details.forced`` so it can never be mistaken for a pass.

    Records are left exactly where they are when they cannot be forced (already
    published, or rejected for embedded text), with the reason reported.
    """
    records = _load_records(db, request.record_ids)

    items: list[ForcedAcceptResultItem] = []
    accepted = 0

    for record in records:
        result = forced_acceptance.force_accept(record, reason=request.reason)
        if result.accepted:
            accepted += 1
        items.append(ForcedAcceptResultItem(**result.__dict__))

    db.commit()

    return ForcedAcceptResponse(
        items=items, accepted=accepted, refused=len(items) - accepted
    )


# --------------------------------------------------------------------------- #
# CSV export (available from Stage 6 onward, including the Gallery)
# --------------------------------------------------------------------------- #

def _csv_response(result: csv_export.CsvBuildResult) -> Response:
    """Render a CSV build result as a download, with its warnings in headers."""
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


def _build_selected_csv(
    request: CsvExportRequest,
    db: Session,
    *,
    apply_names: bool = False,
) -> csv_export.CsvBuildResult:
    if request.record_ids is not None and len(request.record_ids) > MAX_DELIVERY_BATCH:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot export more than {MAX_DELIVERY_BATCH} rows at once.",
        )
    return stage_orchestrator.build_metadata_csv(
        SessionLocal,
        request.record_ids,
        only_ready=request.only_ready,
        # The request's own session, so the export sees exactly the rows this
        # request can see (and so a test's isolated DB is honoured).
        db=db,
        apply_names=apply_names,
    )


@router.post("/api/assets/csv")
async def export_selected_csv(
    request: CsvExportRequest, db: Session = Depends(get_db)
) -> Response:
    """Download the Adobe Stock CSV for a selection (or every eligible record).

    Available from Stage 6 onward *including* the Gallery, because an operator
    uploads from there and needs the CSV at the same moment as the images.
    """
    # A *download* pins the batch-resolved names, so the CSV the operator keeps
    # and the names the UI shows afterwards are the same strings. The write is
    # committed because the operator has now taken delivery of this batch.
    result = _build_selected_csv(request, db, apply_names=True)

    if result.row_count == 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "No exportable rows. Generate metadata for at least one image "
                "before exporting."
            ),
        )

    db.commit()
    return _csv_response(result)


@router.post("/api/assets/csv/preview")
async def preview_selected_csv(
    request: CsvExportRequest, db: Session = Depends(get_db)
) -> dict:
    """Return the CSV text plus warnings without triggering a download."""
    result = _build_selected_csv(request, db)
    return {
        "csv_text": result.csv_text,
        "row_count": result.row_count,
        "skipped": result.skipped,
        "warnings": result.warnings,
    }


# --------------------------------------------------------------------------- #
# Bundle: images + their CSV in one ZIP
# --------------------------------------------------------------------------- #

@router.post("/api/assets/bundle")
async def download_bundle(
    request: CsvExportRequest, db: Session = Depends(get_db)
) -> FileResponse:
    """ZIP the selected images **together with their Adobe Stock CSV**.

    Downloading the images and the CSV separately is how they get out of sync -
    the operator grabs a ZIP from one page and a CSV from another and the
    filenames no longer match. Bundling them makes the pairing structural: the
    CSV inside the archive names exactly the files beside it.
    """
    if not request.record_ids:
        raise HTTPException(
            status_code=400,
            detail="record_ids must not be empty — a bundle needs an explicit selection.",
        )
    if len(request.record_ids) > MAX_ZIP_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot bundle more than {MAX_ZIP_FILES} files at once.",
        )

    records = _load_records(db, request.record_ids)

    # Resolve the file for each record FIRST, then build the CSV from exactly
    # those records.
    #
    # Building the CSV from the *requested* selection instead is a precision bug:
    # a record that contributes no file would add a CSV row for a file that is
    # not in the archive. Adobe matches rows to files by name, so that orphan
    # row is not merely untidy — it is an asset that silently never gets its
    # metadata. The archive and the CSV must describe the same set.
    #
    # Staged file first: a published record's staged copy is the bytes that
    # actually shipped. Otherwise fall back to the working file — publishing
    # is what creates the staged copy, and the gallery's "Ready to publish"
    # records are exactly the ones bundled *before* that happens. The fallback
    # resolves the way publish does (working → original), so the archive
    # carries what a later publish would stage.
    bundled: list[tuple[ImageRecord, Path]] = []
    for record in records:
        path = resolve_ready_path(record, settings.READY_DIR)
        if path is None:
            path = resolve_current_path(record)
        if path is None:
            logger.warning(
                "Skipping record %s in bundle: no staged, working, or "
                "original file on disk",
                record.id,
            )
            continue
        bundled.append((record, path))

    if not bundled:
        raise HTTPException(
            status_code=409,
            detail=(
                "None of the selected records have a file to bundle: no staged "
                "copy exists and neither the working nor the original file is "
                "on disk. You can still download just the CSV."
            ),
        )

    result = stage_orchestrator.build_metadata_csv(
        SessionLocal,
        [record.id for record, _ in bundled],
        # Eligibility was already decided by the file-resolution check above,
        # so the stage filter must not second-guess it: a published asset is
        # not METADATA_READY, and filtering here would empty the CSV of
        # exactly the images the archive contains.
        only_ready=False,
        db=db,
        # Pin the batch-resolved names, so the ZIP entry written below and the
        # CSV row describe the same file. Without this the archive could
        # contain `fleet-of-autonomous-1.jpg` while the CSV named
        # `fleet-of-autonomous-transpor.jpg`.
        apply_names=True,
    )

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False, dir=str(STORAGE_ROOT))
    tmp.close()
    zip_path = Path(tmp.name)

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for record, path in bundled:
                name = asset_naming.effective_download_name(record, path)
                archive.write(path, arcname=name)

            # Only add the CSV when it describes something in the archive.
            if result.row_count > 0:
                archive.writestr(
                    csv_export.build_csv_filename(),
                    csv_export.encode_csv_bytes(result.csv_text),
                )
    except Exception:
        zip_path.unlink(missing_ok=True)
        logger.exception("Failed to build the delivery bundle")
        raise HTTPException(status_code=500, detail="Failed to build the bundle.")

    # The names above are now part of the delivered artifact, so record them: a
    # later re-export of the same batch must produce the same filenames.
    db.commit()

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename="adobe-stock-delivery.zip",
        background=BackgroundTask(lambda: zip_path.unlink(missing_ok=True)),
    )
