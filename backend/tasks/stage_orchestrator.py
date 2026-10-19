"""Stage orchestrator - drives records through the seven-stage pipeline.

Each public ``run_*`` function is a batch operation over an explicit list of
record ids. They share one contract:

* They never raise for a per-record failure; a broken image is marked ``failed``
  in the job report while the rest of the batch continues.
* They persist their outcome on the record (``stage``, ``working_path``,
  ``acceptance_report``, ``stage_details``) before returning.
* They are safe to re-run: a record already past a stage is skipped, not
  reprocessed.

The functions are plain synchronous callables so FastAPI's ``BackgroundTasks``
can dispatch them after the HTTP response is sent.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy.orm import Session

from config import Settings, settings as default_settings
from models import ImageLifecycleState, ImageRecord, ImageStatus, PipelineStage, utcnow
from services import (
    compatibility_checker,
    csv_export,
    gemini_auditor,
    gemini_metadata,
    ocr_scanner,
    prompt_context,
    record_metrics,
    upscaler,
)
from services.acceptance.scorer import AcceptanceConfig
from services.image_lifecycle import DELIVERABLE_STATES, refresh_state_for_stage
from services.jobs import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    Job,
    JobItem,
    registry,
)
from services.refine import refine_image
from services.stage_registry import TERMINAL_STAGES
from services.upscale.options import UpscaleOptions, capacity_label

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

#: Stages that block Stage 6 metadata generation.
#:
#: Deliberately *not* every terminal stage. A below-threshold (``INCOMPATIBLE``)
#: record is a judgement call the operator may override, and Stage 6 must still
#: be able to name it. ``OCR_REJECTED`` is a content-policy violation, so it is
#: excluded from the deliverable pipeline entirely. ``QUARANTINED`` is a
#: diversity-gate rejection: it must not be named or uploaded either.
METADATA_BLOCKED_STAGES: frozenset[PipelineStage] = frozenset(
    {PipelineStage.OCR_REJECTED, PipelineStage.QUARANTINED}
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _current_path(record: ImageRecord) -> Path:
    """The file the pipeline should operate on right now.

    Falls back to the inbox original whenever no upscaled/refined copy exists,
    so a record is never stranded by a missing intermediate file.
    """
    for candidate in (record.working_path, record.original_path):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(record.original_path or "")


def _set_stage(
    record: ImageRecord,
    stage: PipelineStage,
    *,
    detail_key: str | None = None,
    detail: dict | None = None,
) -> None:
    """Advance a record to ``stage``, recording an optional per-stage detail."""
    record.stage = stage
    # Reaching the stage satisfies any pending queue entry for it.
    record.queued_stage = None
    record.stage_updated_at = utcnow()
    if detail_key and detail is not None:
        details = dict(record.stage_details or {})
        details[detail_key] = detail
        # Reassign so SQLAlchemy detects the JSON mutation.
        record.stage_details = details


def _upscale_source_path(record: ImageRecord, cfg: Settings) -> Path:
    """The file Stage 3 should read: the best copy that is not its own output.

    Re-running Stage 3 must not feed a previous upscale back into the model.
    Chaining passes would inflate the file for no added detail, and it would
    make the before/after view compare an image against itself. So a prior
    upscaled output is skipped in favour of the refined or original copy.
    """
    previous_output = Path(cfg.UPSCALED_DIR) / f"{record.id}-upscaled.jpg"
    candidates = (
        record.working_path,
        Path(cfg.REFINED_DIR) / f"{record.id}-refined.jpg",
        record.original_path,
    )
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path == previous_output:
            continue
        if path.exists():
            return path
    return Path(record.original_path or "")


def _load_records(db: Session, record_ids: Iterable[str]) -> tuple[list[ImageRecord], list[str]]:
    """Fetch records in the caller's order, reporting ids that do not exist."""
    ids = list(dict.fromkeys(record_ids))
    if not ids:
        return [], []
    records = db.query(ImageRecord).filter(ImageRecord.id.in_(ids)).all()
    by_id = {record.id: record for record in records}
    ordered = [by_id[rid] for rid in ids if rid in by_id]
    missing = [rid for rid in ids if rid not in by_id]
    return ordered, missing


def _make_items(records: list[ImageRecord]) -> list[JobItem]:
    return [
        JobItem(record_id=record.id, filename=record.filename) for record in records
    ]


def _start_job(
    job_id: str | None, stage: str, kind: str, records: list[ImageRecord]
) -> Job:
    """Adopt a job created by the API layer, or create one for direct calls.

    The router registers the job *before* dispatching the background task so it
    can return a real job id in the HTTP response; direct callers (tests, CLI)
    omit ``job_id`` and get a freshly created one.
    """
    if job_id:
        existing = registry.get(job_id)
        if existing is not None:
            return existing

    return registry.create(stage, kind, _make_items(records))


def _should_stop(job: Job) -> bool:
    return job.cancel_requested


def _existing_metadata(record: ImageRecord) -> dict | None:
    """Return a record's Stage 6 metadata in the approval pipeline's shape.

    Returns None when no title exists, which tells the approval pipeline to
    generate metadata itself instead of embedding an empty caption.
    """
    title = (record.generated_title or "").strip()
    if not title:
        return None

    return {
        "title": title,
        "description": (record.generated_description or "").strip() or title,
        "keywords": [str(keyword) for keyword in (record.generated_keywords or [])],
    }


# --------------------------------------------------------------------------- #
# Stage 2 - OCR sweep
# --------------------------------------------------------------------------- #

def run_ocr_stage(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    job_id: str | None = None,
) -> str:
    """Scan records for embedded text (Stage 2).

    Records are read from the *inbox original* rather than the working copy,
    because OCR is the first inspection and the original is the authoritative
    source. Images with blocking text land in ``OCR_REJECTED`` and are excluded
    from every later stage.

    Returns the job id.
    """
    cfg = settings or default_settings
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "ocr", "ocr-scan", records)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            # Re-running OCR on an already-scanned record is wasted work.
            if record.stage in (PipelineStage.OCR_CLEAR, PipelineStage.OCR_REJECTED):
                item.status = "skipped"
                item.message = f"Already scanned ({record.stage.value})."
                item.finished_at = time.time()
                continue

            try:
                result = ocr_scanner.scan_text(_current_path(record))

                record.ocr_text_detected = result.text_detected
                record.ocr_text_content = (result.text or "")[:2000] or None

                if result.blocked:
                    _set_stage(
                        record,
                        PipelineStage.OCR_REJECTED,
                        detail_key="ocr",
                        detail=result.to_dict(),
                    )
                    # OCR rejection is terminal: keep it out of the PASSED queue.
                    record.status = ImageStatus.FLAGGED
                    refresh_state_for_stage(record)
                    record.semantic_flags = [result.reason or "Text detected"]
                    item.status = "failed"
                    item.message = result.reason or "Text detected."
                else:
                    _set_stage(
                        record,
                        PipelineStage.OCR_CLEAR,
                        detail_key="ocr",
                        detail=result.to_dict(),
                    )
                    item.status = "succeeded"
                    item.message = (
                        result.reason
                        or f"No text detected ({result.classification})."
                    )

                item.finished_at = time.time()
                db.commit()
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
                logger.exception("OCR failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"OCR error: {exc}"
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 3 - Upscale
# --------------------------------------------------------------------------- #

def _upscale_label(options: UpscaleOptions, cfg: Settings) -> str:
    """One-line summary of the Stage 3 configuration, shown above the bar."""
    bits = [
        f"Upscaling to {capacity_label(options.target_long_edge)}",
        f"model {options.model} ({options.model_scale}x)",
        f"GPU {options.gpu_id}",
    ]
    if options.tta:
        bits.append("TTA")
    if options.tile_size:
        bits.append(f"tile {options.tile_size}")
    return " · ".join(bits)


def run_upscale_stage(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    job_id: str | None = None,
    options: UpscaleOptions | dict | None = None,
) -> str:
    """Upscale records that cleared OCR (Stage 3). Returns the job id.

    Args:
        options: A validated :class:`UpscaleOptions`, a raw request dict, or
            None for the configured defaults. Applied to the whole batch, since
            the Stage 3 panel configures one run rather than per-image settings.
    """
    cfg = settings or default_settings
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "upscale", "upscale", records)

        resolved = upscaler.from_payload(options, cfg) if isinstance(options, dict) else options
        if resolved is None:
            resolved = upscaler.default_options(cfg)
        job.progress_label = _upscale_label(resolved, cfg)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            if record.stage in TERMINAL_STAGES:
                item.status = "skipped"
                item.message = f"Terminal stage ({record.stage.value})."
                item.finished_at = time.time()
                continue

            if record.stage in (
                PipelineStage.UPSCALED,
                PipelineStage.REFINED,
                PipelineStage.COMPATIBLE,
                PipelineStage.METADATA_READY,
                PipelineStage.PUBLISHED,
            ):
                item.status = "skipped"
                item.message = f"Already past Stage 3 ({record.stage.value})."
                item.finished_at = time.time()
                continue

            try:
                # The CLI streams a percentage per image, so forward it into the
                # job report instead of leaving the UI on a static spinner.
                def _on_progress(percent: float, label: str, _id: str = record.id) -> None:
                    job.report_progress(_id, percent, label)

                result = upscaler.upscale_image(
                    _upscale_source_path(record, cfg),
                    cfg.UPSCALED_DIR,
                    record.id,
                    options=resolved,
                    settings=cfg,
                    on_progress=_on_progress,
                )

                if not result.success:
                    # Upscaling is an enhancement, not a hard gate: keep the
                    # record moving with its current file and record the reason.
                    _set_stage(
                        record,
                        PipelineStage.UPSCALED,
                        detail_key="upscale",
                        detail=result.to_dict(),
                    )
                    item.status = "succeeded"
                    item.message = f"Upscale unavailable: {result.reason}"
                else:
                    if result.output_path and result.backend != upscaler.BACKEND_SKIPPED:
                        record.working_path = result.output_path
                        # The delivered file just changed, so the reported
                        # geometry must follow it. Measuring only at ingestion is
                        # what made an 8.2 MP asset report 1.06 MP - the original
                        # upload's dimensions - and look like the upscale had
                        # shrunk it.
                        record_metrics.refresh_delivery_metrics(record, cfg)
                    _set_stage(
                        record,
                        PipelineStage.UPSCALED,
                        detail_key="upscale",
                        detail=result.to_dict(),
                    )
                    item.status = "succeeded"
                    model_note = f" · {result.model}" if result.model else ""
                    item.message = (
                        f"{result.backend}{model_note} · "
                        f"{result.source_megapixels:.1f} MP → "
                        f"{result.output_megapixels:.1f} MP"
                    )

                item.progress = 100.0
                item.finished_at = time.time()
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Upscale failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Upscale error: {exc}"
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 4 - Refine
# --------------------------------------------------------------------------- #

def run_refine_stage(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    use_semantic: bool = True,
    job_id: str | None = None,
) -> str:
    """Refine records until they reach the acceptance threshold (Stage 4).

    The semantic audit runs first (when enabled) so its score is available to
    every refinement pass; a correction that fixes a pixel metric but leaves the
    model unconvinced should not be treated as progress.

    Returns the job id.
    """
    cfg = settings or default_settings
    acceptance = AcceptanceConfig.from_settings()
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "refine", "refine", records)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            if record.stage in TERMINAL_STAGES:
                item.status = "skipped"
                item.message = f"Terminal stage ({record.stage.value})."
                item.finished_at = time.time()
                continue

            try:
                source = _current_path(record)

                semantic: dict | None = None
                if use_semantic:
                    semantic = gemini_auditor.audit_image(
                        source, api_key=cfg.effective_llm_api_key
                    )

                result = refine_image(
                    source,
                    cfg.REFINED_DIR,
                    record.id,
                    semantic=semantic,
                    settings=cfg,
                    config=acceptance,
                )

                if result.output_path:
                    record.working_path = result.output_path
                    # A refine pass can change the geometry too (and always
                    # rewrites the file), so the delivered metrics are re-measured
                    # rather than left describing the pre-refine file.
                    record_metrics.refresh_delivery_metrics(record, cfg)
                record.refine_passes = result.passes
                if result.report is not None:
                    record.acceptance_report = result.report.to_dict()
                    record.acceptance_score = result.report.score

                _set_stage(
                    record,
                    PipelineStage.REFINED,
                    detail_key="refine",
                    detail=result.to_dict(),
                )

                item.score = result.final_score
                item.status = "succeeded"
                item.message = (
                    f"{result.initial_score:.1%} → {result.final_score:.1%} "
                    f"in {result.passes} pass(es)"
                )
                item.finished_at = time.time()
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Refine failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Refine error: {exc}"
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 5 - Compatibility gate
# --------------------------------------------------------------------------- #

def run_compatibility_stage(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    use_semantic: bool = True,
    job_id: str | None = None,
) -> str:
    """Run the full acceptance algorithm and gate records (Stage 5).

    Passing records become ``COMPATIBLE`` with ``status=PASSED`` so they enter
    the existing approval/download flow. Failing records become
    ``INCOMPATIBLE`` with ``status=FLAGGED`` and carry remediation advice.

    Returns the job id.
    """
    cfg = settings or default_settings
    acceptance = AcceptanceConfig.from_settings()
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "compatibility", "compatibility-check", records)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            if record.stage in TERMINAL_STAGES:
                item.status = "skipped"
                item.message = f"Terminal stage ({record.stage.value})."
                item.finished_at = time.time()
                continue

            try:
                source = _current_path(record)

                semantic: dict | None = None
                if use_semantic:
                    semantic = gemini_auditor.audit_image(
                        source, api_key=cfg.effective_llm_api_key
                    )

                verdict = compatibility_checker.check_compatibility(
                    source, semantic=semantic, config=acceptance
                )

                record.acceptance_report = verdict.report.to_dict()
                record.acceptance_score = verdict.report.score
                record.semantic_confidence_score = (
                    semantic.get("confidence_score") if semantic else None
                )
                record.semantic_flags = (
                    [str(flag) for flag in (semantic or {}).get("flags", [])]
                    or [issue.detail for issue in verdict.report.issues]
                )

                if verdict.passed:
                    _set_stage(
                        record,
                        PipelineStage.COMPATIBLE,
                        detail_key="compatibility",
                        detail=verdict.to_dict(),
                    )
                    record.status = ImageStatus.PASSED
                    item.status = "succeeded"
                    item.message = verdict.summary
                else:
                    _set_stage(
                        record,
                        PipelineStage.INCOMPATIBLE,
                        detail_key="compatibility",
                        detail=verdict.to_dict(),
                    )
                    record.status = ImageStatus.FLAGGED
                    refresh_state_for_stage(record)
                    item.status = "failed"
                    item.message = verdict.summary

                item.score = verdict.report.score
                item.finished_at = time.time()
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Compatibility check failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Compatibility error: {exc}"
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 6 - Metadata generation
# --------------------------------------------------------------------------- #

def run_metadata_stage(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    delay_seconds: float | None = None,
    job_id: str | None = None,
) -> str:
    """Generate title/description/keywords/category one record at a time.

    Calls are deliberately serialized with a configurable pause: the gateway
    routes to free upstream models that rate-limit aggressively, and a burst of
    parallel requests is the fastest way to get throttled.

    Returns the job id.
    """
    cfg = settings or default_settings
    # Stored setting first (Settings page), then .env, then the built-in.
    from services import app_settings

    pause = (
        float(delay_seconds)
        if delay_seconds is not None
        else app_settings.resolve_metadata().delay_seconds
    )
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "metadata", "metadata-generate", records)

        for index, record in enumerate(records):
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            # Only a content-policy rejection blocks metadata generation.
            #
            # The acceptance gate is a heuristic, so a below-threshold record is
            # a *judgement call* the operator is entitled to make - refusing to
            # even generate a title for it turned the gate into an absolute dead
            # end. OCR_REJECTED is different in kind: embedded text is a
            # content-policy violation, not a quality opinion, so it stays blocked.
            if record.stage in METADATA_BLOCKED_STAGES:
                item.status = "skipped"
                item.message = (
                    "Embedded text was detected — a content-policy rejection, "
                    "not a quality judgement."
                )
                item.finished_at = time.time()
                continue

            try:
                metadata = gemini_metadata.generate_metadata(
                    _current_path(record),
                    api_key=cfg.effective_llm_api_key,
                    # The original name, not the stored path: at this point
                    # the file on disk is a uuid/record-id copy, while
                    # `filename` is what the image was uploaded as - often a
                    # brief description of what it depicts.
                    original_filename=record.filename,
                    # The brief this image was generated from, when one was
                    # bound to the record; "" (no binding / deleted row) is
                    # rendered as nothing and the prompt stays vision+name.
                    generation_prompt=prompt_context.brief_for(
                        db, record.prompt_id
                    ),
                )

                if not metadata:
                    item.status = "failed"
                    item.message = "The metadata model returned nothing usable."
                    item.finished_at = time.time()
                    continue

                record.generated_title = (metadata.get("title") or "")[:500] or None
                record.generated_description = metadata.get("description") or None
                record.generated_keywords = metadata.get("keywords") or []
                record.category = metadata.get("category")
                # The model named the asset while looking at it. Stored as a
                # *proposal* only - it never becomes the delivered filename until
                # the operator applies it - so a batch can be reviewed first.
                record.suggested_filename = metadata.get("suggested_filename") or None

                _set_stage(
                    record,
                    PipelineStage.METADATA_READY,
                    detail_key="metadata",
                    detail={
                        "keyword_count": len(record.generated_keywords or []),
                        "category": record.category,
                        "generated_at": utcnow().isoformat(),
                        "suggested_filename": record.suggested_filename,
                    },
                )
                # Stage 6 complete = the pipeline passed: APPROVED (or stays
                # put when the operator had already queued/accepted it).
                refresh_state_for_stage(record)

                item.status = "succeeded"
                item.message = (
                    f"{len(record.generated_keywords or [])} keywords · "
                    f"category {record.category}"
                )
                item.finished_at = time.time()
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Metadata generation failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Metadata error: {exc}"
                item.finished_at = time.time()

            # Pause between calls to stay under the upstream rate limit. Skip
            # the wait after the final record so the job finishes promptly.
            is_last = index == len(records) - 1
            if pause > 0 and not is_last and not _should_stop(job):
                time.sleep(pause)

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 7 - Publish to the gallery
# --------------------------------------------------------------------------- #

def publish_records(
    db_session_factory: SessionFactory,
    record_ids: list[str],
    settings: Settings | None = None,
    *,
    job_id: str | None = None,
) -> str:
    """Stage records for upload and move them to the gallery (Stage 7).

    Reuses the existing approval pipeline (metadata generation if missing, copy
    into ``ready_to_upload``, ExifTool embedding) so there is exactly one code
    path that produces a downloadable asset.

    Returns the job id.
    """
    from tasks.audit_orchestrator import process_approval

    cfg = settings or default_settings
    db = db_session_factory()
    job: Job | None = None

    try:
        records, missing = _load_records(db, record_ids)
        job = _start_job(job_id, "gallery", "publish", records)

        for record in records:
            item = next(i for i in job.items if i.record_id == record.id)
            if _should_stop(job):
                item.status = "skipped"
                item.message = "Cancelled."
                continue

            item.status = "running"
            item.started_at = time.time()

            if record.stage == PipelineStage.PUBLISHED:
                item.status = "skipped"
                item.message = "Already published."
                item.finished_at = time.time()
                continue

            # Stage 7 is gated by the *manual* queue, not by Stage 6: an image
            # uploads only when the operator queued it (approve / PATCH state).
            if record.state != ImageLifecycleState.READY_TO_PUBLISH:
                item.status = "failed"
                item.message = (
                    "Record must be queued for publish first "
                    f"(state READY_TO_PUBLISH); record is in {record.state.value}."
                )
                item.finished_at = time.time()
                continue

            try:
                # Reuse the metadata already generated in Stage 6 rather than
                # paying for a second LLM call, but only when it is complete
                # enough to embed.
                override = None
                if refreshed_metadata := _existing_metadata(record):
                    override = refreshed_metadata

                success = process_approval(
                    db_session_factory=db_session_factory,
                    record_id=record.id,
                    settings=cfg,
                    override_metadata=override,
                )
                db.expire_all()
                refreshed = db.query(ImageRecord).filter(
                    ImageRecord.id == record.id
                ).first()

                if success and refreshed is not None:
                    _set_stage(
                        refreshed,
                        PipelineStage.PUBLISHED,
                        detail_key="publish",
                        detail={"published_at": utcnow().isoformat()},
                    )
                    refreshed.status = ImageStatus.READY
                    # Published — unless Adobe already accepted it, which
                    # outranks a (re)publish.
                    if refreshed.state != ImageLifecycleState.AS_ACCEPTED:
                        refreshed.state = ImageLifecycleState.PUBLISHED
                    db.commit()
                    item.status = "succeeded"
                    item.message = "Staged in ready_to_upload."
                else:
                    item.status = "failed"
                    item.message = "Approval pipeline failed (copy or metadata embedding)."
                item.finished_at = time.time()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Publish failed for record %s", record.id)
                db.rollback()
                item.status = "failed"
                item.message = f"Publish error: {exc}"
                item.finished_at = time.time()

        if missing:
            job.message = f"{len(missing)} record(s) not found."

        status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
        registry.finish(job, status)
        return job.id
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Stage 6 - CSV export
# --------------------------------------------------------------------------- #

def build_metadata_csv(
    db_session_factory: SessionFactory,
    record_ids: list[str] | None = None,
    *,
    only_ready: bool = True,
    db: Session | None = None,
    apply_names: bool = False,
) -> csv_export.CsvBuildResult:
    """Build the Adobe Stock CSV for the given records.

    When ``record_ids`` is omitted every eligible record is included, which is
    what the "download the whole batch" action needs.

    ``only_ready`` restricts the set to the lifecycle states Adobe upload
    covers — queued, published, or accepted. It is on by default because Adobe
    matches rows to files by name and only a deliverable asset belongs in the
    CSV; the caller can turn it off when the operator deliberately exports a
    selected set that has not been queued yet.

    ``db`` lets an HTTP caller pass the session FastAPI already opened. Without
    it the function opens its own session from ``db_session_factory``, which in
    tests means the **real** database rather than the isolated one the request
    dependency injected — so a record created through the test client was
    invisible to its own CSV export.

    ``apply_names`` pins the batch-resolved filenames onto the records, which a
    *download* needs (so the ZIP entry matches its CSV row) but a *preview* must
    not do.
    """
    owns_session = db is None
    session = db if db is not None else db_session_factory()
    try:
        query = session.query(ImageRecord)
        if record_ids:
            query = query.filter(ImageRecord.id.in_(list(dict.fromkeys(record_ids))))
        if only_ready:
            query = query.filter(ImageRecord.state.in_(sorted(DELIVERABLE_STATES)))

        # Ordered, not merely sorted: `created_at` is stored at microsecond
        # resolution and two records inserted in the same call share a value, so
        # without the id tiebreak two identical requests could emit their rows in
        # different orders. The CSV is a delivered artifact, so the same selection
        # must produce the same file every time.
        records = (
            query.order_by(ImageRecord.created_at.asc(), ImageRecord.id.asc()).all()
        )
        return csv_export.build_csv(records, apply_names=apply_names)
    finally:
        # Only close a session this function opened.
        if owns_session:
            session.close()
