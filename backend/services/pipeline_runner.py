"""Pipeline runner - executes a batch's picked steps in canonical order.

A batch declares ``steps: [{key, config}]``; this module walks them in the
canonical order defined by :mod:`services.pipeline_defs` and runs each one over
the batch's records, writing per-step status into ``batch.step_progress`` as it
goes so the processing page can poll a single endpoint.

Contracts (mirroring the stage orchestrator's):

* A per-record failure never aborts the batch — it lands in the step's counts.
* A step-level failure (an exception, a missing dependency) stops the batch and
  marks it ``failed`` with the reason, so the UI never shows a job that hung.
* Cancellation is cooperative: the cancel endpoint flags the batch *and* the
  in-flight step job; the runner stops between steps and the stage runners stop
  between records.

Steps dispatch to the existing stage runners wherever an equivalent exists, so
the batch pipeline and the legacy stage workspace cannot drift apart on what a
step actually does.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Callable

from PIL import Image
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from config import Settings, settings as default_settings
from models import Batch, ImageRecord, PipelineStage, utcnow
from services import (
    bg_remover,
    edge_quality,
    pipeline_defs,
    png_ops,
    record_metrics,
    step_progress,
)
from services.jobs import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    Job,
    JobItem,
    registry,
)
from services.stage_registry import TERMINAL_STAGES
from tasks import stage_orchestrator

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

#: batch_id -> the in-flight step job, so cancel can reach mid-step.
_active_jobs: dict[str, str] = {}
_active_lock = threading.Lock()

#: Records already at these stages have been upscaled; re-running wastes a pass.
_UPSCALED_STAGES = (
    PipelineStage.UPSCALED,
    PipelineStage.REFINED,
    PipelineStage.COMPATIBLE,
    PipelineStage.METADATA_READY,
    PipelineStage.PUBLISHED,
)


# --------------------------------------------------------------------------- #
# Cancel plumbing
# --------------------------------------------------------------------------- #

def request_cancel(batch_id: str) -> bool:
    """Flag the in-flight step job for a running batch. Returns True if found."""
    with _active_lock:
        job_id = _active_jobs.get(batch_id)
    if not job_id:
        return False
    return registry.cancel(job_id)


def recover_interrupted_batches(engine: Engine) -> int:
    """Mark batches left ``running`` by a server restart as failed.

    Jobs live in memory, so a restart orphans every running batch — without
    this repair the UI would show it as running forever and refuse to re-run.
    """
    with engine.begin() as connection:
        result = connection.execute(
            text(
                "UPDATE batches SET status = 'failed', "
                "error = 'Interrupted by a server restart.' "
                "WHERE status = 'running'"
            )
        )
        return result.rowcount or 0


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _current_path(record: ImageRecord) -> Path:
    """The file the next step should read (working copy, else the original)."""
    for candidate in (record.working_path, record.original_path):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(record.original_path or "")


def _start_step_job(key: str, records: list[ImageRecord]) -> Job:
    """Register a job whose items cover exactly the batch's records."""
    return registry.create(
        key,
        f"batch-{key}",
        [JobItem(record_id=record.id, filename=record.filename) for record in records],
    )


def _counts(job: Job) -> dict:
    out = {"succeeded": 0, "failed": 0, "skipped": 0, "pending": 0}
    for item in job.items:
        out[item.status] = out.get(item.status, 0) + 1
    return out


def _counts_message(counts: dict) -> str:
    parts = [f"{counts.get('succeeded', 0)} ok"]
    if counts.get("failed"):
        parts.append(f"{counts['failed']} failed")
    if counts.get("skipped"):
        parts.append(f"{counts['skipped']} skipped")
    return " · ".join(parts)


def _outcome_for_job(job: Job, counts: dict) -> dict:
    if job.status == STATUS_CANCELLED:
        status = "cancelled"
    elif job.status == STATUS_FAILED:
        status = "failed"
    else:
        status = "completed"
    counts_msg = _counts_message(counts)
    # One message, not two: fold the counts in exactly once so the UI does not
    # render "1 ok · 1 ok" by appending them again.
    message = f"{job.message} · {counts_msg}" if job.message else counts_msg
    return {"status": status, "message": message, "counts": counts}


# --------------------------------------------------------------------------- #
# Custom steps (no legacy equivalent)
# --------------------------------------------------------------------------- #

def _step_bg_remove(
    db_factory: SessionFactory,
    records: list[ImageRecord],
    config: dict,
    job: Job,
    cfg: Settings,
) -> dict:
    """Cut the object out of every record; optionally check the edge quality."""
    # Fail fast with a readable error: a missing package is an environment
    # problem, not a per-record one, and silently failing every record would
    # read as "my images are broken".
    try:
        import rembg  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "Background removal requires the 'rembg' package "
            "(pip install rembg)."
        ) from exc

    model = str(config.get("model") or bg_remover.DEFAULT_MODEL)
    edge_check = bool(config.get("edge_check", True))

    for record in records:
        item = next(i for i in job.items if i.record_id == record.id)
        if job.cancel_requested:
            item.status = "skipped"
            item.message = "Cancelled."
            continue

        item.status = "running"
        item.started_at = time.time()
        try:
            source = _current_path(record)
            result = bg_remover.remove_background(source, record.id, model=model, cfg=cfg)
            if not result.success:
                item.status = "failed"
                item.message = result.reason
                item.finished_at = time.time()
                continue

            detail = dict(result.to_dict())
            if edge_check and result.output_path:
                report = edge_quality.check_edges(result.output_path)
                detail["edge_quality"] = report.to_dict()

            record.working_path = result.output_path
            # Regenerate the thumbnail so the grid shows the cut-out, not the
            # original with its background. A *transparent* PNG thumb: the
            # gallery renders the object over the card's own background.
            thumb = png_ops.alpha_thumbnail(
                result.output_path,
                cfg.THUMBNAILS_DIR,
                Path(record.thumbnail_path).stem.removeprefix("thumb_")
                if record.thumbnail_path
                else record.id,
            )
            if thumb:
                record.thumbnail_path = thumb

            details = dict(record.stage_details or {})
            details["bg_remove"] = detail
            record.stage_details = details  # reassign: JSON mutation is not tracked
            record.stage_updated_at = utcnow()
            record_metrics.refresh_delivery_metrics(record, cfg)

            verdict = (detail.get("edge_quality") or {}).get("verdict")
            item.status = "succeeded"
            item.message = f"{result.model} · edges {verdict}" if verdict else result.model
            item.finished_at = time.time()
            db = db_factory()
            try:
                db.merge(record)
                db.commit()
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
            logger.exception("Background removal failed for record %s", record.id)
            item.status = "failed"
            item.message = f"Background removal error: {exc}"
            item.finished_at = time.time()

    counts = _counts(job)
    status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
    registry.finish(job, status)
    return _outcome_for_job(job, counts)


def _step_upscale_png(
    db_factory: SessionFactory,
    records: list[ImageRecord],
    config: dict,
    job: Job,
    cfg: Settings,
) -> dict:
    """Alpha-preserving Lanczos upscale for PNG batches.

    The neural CLI only writes JPEG, which would destroy the alpha channel that
    *is* the deliverable of a PNG batch, so the PNG path resamples the RGBA
    image directly. The step description in the UI says so honestly.
    """
    import time

    target = int(config.get("target_long_edge") or 3840)
    out_dir = Path(cfg.UPSCALED_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    for record in records:
        item = next(i for i in job.items if i.record_id == record.id)
        if job.cancel_requested:
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
        if record.stage in _UPSCALED_STAGES:
            item.status = "skipped"
            item.message = f"Already upscaled ({record.stage.value})."
            item.finished_at = time.time()
            continue

        try:
            source = _current_path(record)
            with Image.open(source) as probe:
                src_w, src_h = probe.size
            resized = png_ops.upscale_rgba_to_long_edge(source, target)
            out_path = out_dir / f"{record.id}-upscaled.png"
            resized.save(out_path, "PNG")

            record.working_path = str(out_path)
            record_metrics.refresh_delivery_metrics(record, cfg)
            details = dict(record.stage_details or {})
            details["upscale"] = {
                "backend": "lanczos-rgba",
                "target_long_edge": target,
                "width": resized.width,
                "height": resized.height,
                "alpha_preserved": True,
            }
            record.stage_details = details
            record.stage = PipelineStage.UPSCALED
            record.queued_stage = None
            record.stage_updated_at = utcnow()

            src_mp = round(src_w * src_h / 1_000_000, 2)
            out_mp = round(resized.width * resized.height / 1_000_000, 2)
            item.status = "succeeded"
            item.message = f"Lanczos (alpha preserved) · {src_mp} MP → {out_mp} MP"
            item.progress = 100.0
            item.finished_at = time.time()
            db = db_factory()
            try:
                db.merge(record)
                db.commit()
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("PNG upscale failed for record %s", record.id)
            item.status = "failed"
            item.message = f"Upscale error: {exc}"
            item.finished_at = time.time()

    counts = _counts(job)
    status = STATUS_CANCELLED if job.cancel_requested else STATUS_COMPLETED
    registry.finish(job, status)
    return _outcome_for_job(job, counts)


# --------------------------------------------------------------------------- #
# Dispatch to the legacy stage runners
# --------------------------------------------------------------------------- #

def _run_stage_step(
    key: str,
    db_factory: SessionFactory,
    record_ids: list[str],
    config: dict,
    job: Job,
    cfg: Settings,
) -> dict:
    """Run a step by delegating to its stage-orchestrator runner."""
    runners = {
        "ocr": stage_orchestrator.run_ocr_stage,
        "refine": stage_orchestrator.run_refine_stage,
        "compatibility": stage_orchestrator.run_compatibility_stage,
        "metadata": stage_orchestrator.run_metadata_stage,
    }
    kwargs: dict = {"job_id": job.id}
    if key in ("refine", "compatibility"):
        kwargs["use_semantic"] = bool(config.get("use_semantic", True))
    elif key == "metadata":
        kwargs["delay_seconds"] = config.get("delay_seconds")

    if key == "upscale":  # raster only; PNG dispatches to _step_upscale_png
        runner = stage_orchestrator.run_upscale_stage
        kwargs["options"] = {
            k: v for k, v in config.items() if v is not None
        } or None
    else:
        runner = runners[key]

    runner(db_factory, record_ids, cfg, **kwargs)

    finished = registry.get(job.id) or job
    counts = _counts(finished)
    return _outcome_for_job(finished, counts)


_DISPATCH: dict[str, Callable[..., dict]] = {
    "bg_remove": _step_bg_remove,
    "ocr": lambda db_f, recs, cfg_d, job, cfg: _run_stage_step(
        "ocr", db_f, [r.id for r in recs], cfg_d, job, cfg
    ),
    "upscale": lambda db_f, recs, cfg_d, job, cfg: _run_stage_step(
        "upscale", db_f, [r.id for r in recs], cfg_d, job, cfg
    ),
    "refine": lambda db_f, recs, cfg_d, job, cfg: _run_stage_step(
        "refine", db_f, [r.id for r in recs], cfg_d, job, cfg
    ),
    "compatibility": lambda db_f, recs, cfg_d, job, cfg: _run_stage_step(
        "compatibility", db_f, [r.id for r in recs], cfg_d, job, cfg
    ),
    "metadata": lambda db_f, recs, cfg_d, job, cfg: _run_stage_step(
        "metadata", db_f, [r.id for r in recs], cfg_d, job, cfg
    ),
}


def _dispatch(key: str, db_factory, records, config, job, cfg, media_type) -> dict:
    if key == "upscale" and media_type == "png":
        return _step_upscale_png(db_factory, records, config, job, cfg)
    step_fn = _DISPATCH.get(key)
    if step_fn is None:
        raise ValueError(f"Unknown step '{key}'.")
    return step_fn(db_factory, records, config, job, cfg)


# --------------------------------------------------------------------------- #
# Batch state persistence
# --------------------------------------------------------------------------- #

def _persist(
    db_factory: SessionFactory,
    batch_id: str,
    *,
    progress: dict | None = None,
    status: str | None = None,
    error: str | None = None,
    finish: bool = False,
) -> None:
    db = db_factory()
    try:
        batch = db.get(Batch, batch_id)
        if batch is None:
            return
        if progress is not None:
            batch.step_progress = dict(progress)
        # An operator cancel wins: the runner never overwrites it.
        if status and batch.status != "cancelled":
            batch.status = status
        if error is not None and batch.status != "cancelled":
            batch.error = error or None  # "" clears a previous error
        if finish and batch.finished_at is None:
            batch.finished_at = utcnow()
        db.commit()
    finally:
        db.close()


def _current_status(db_factory: SessionFactory, batch_id: str) -> str | None:
    db = db_factory()
    try:
        row = db.execute(
            text("SELECT status FROM batches WHERE id = :id"), {"id": batch_id}
        ).fetchone()
        return row[0] if row else None
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def run_batch(
    db_factory: SessionFactory,
    batch_id: str,
    settings: Settings | None = None,
) -> None:
    """Run every picked step of a batch, in canonical order.

    Never raises: a step-level failure marks the batch ``failed`` and stops, so
    a FastAPI background task cannot die silently with the UI polling forever.
    """
    cfg = settings or default_settings

    # Phase 1: load everything we need, then release the session so the step
    # runners do not contend with an open transaction on SQLite.
    db = db_factory()
    try:
        batch = db.get(Batch, batch_id)
        if batch is None:
            logger.error("Batch %s not found; nothing to run.", batch_id)
            return
        try:
            steps = pipeline_defs.normalise_steps(batch.steps, batch.media_type, cfg)
        except ValueError as exc:
            _persist(db_factory, batch_id, status="failed", error=str(exc), finish=True)
            return
        records = (
            db.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch_id)
            .order_by(ImageRecord.created_at)
            .all()
        )
        record_ids = [record.id for record in records]
        media_type = batch.media_type
    finally:
        db.close()

    if not record_ids:
        _persist(
            db_factory,
            batch_id,
            status="failed",
            error="This batch has no images.",
            finish=True,
        )
        return

    progress: dict = {
        step["key"]: {"status": "pending", "message": "", "counts": None}
        for step in steps
    }
    _persist(db_factory, batch_id, progress=progress, status="running", error="")

    batch_failed: str | None = None
    cancelled = False

    for index, step in enumerate(steps):
        key = step["key"]
        config = step["config"]

        if _current_status(db_factory, batch_id) == "cancelled":
            cancelled = True
            for remaining in steps[index:]:
                progress[remaining["key"]] = {
                    "status": "cancelled",
                    "message": "Cancelled before this step started.",
                    "counts": None,
                }
            break

        progress[key] = {"status": "running", "message": "Starting…", "counts": None}
        _persist(db_factory, batch_id, progress=progress)

        step_records = _load_records(db_factory, record_ids)
        job = _start_step_job(key, records=step_records)
        with _active_lock:
            _active_jobs[batch_id] = job.id

        # Sample the job while the step runs so the UI sees counts advance
        # instead of sitting on "Starting…" until the whole step finishes.
        monitor = step_progress.StepProgressMonitor(
            job,
            snapshot=lambda msg, counts: {
                "status": "running",
                "message": msg,
                "counts": counts,
            },
            publish=lambda snap: _persist(
                db_factory, batch_id, progress={**progress, key: snap}
            ),
        ).start()

        try:
            outcome = _dispatch(key, db_factory, step_records, config, job, cfg, media_type)
            # Stop sampling *before* persisting the outcome: a late monitor
            # tick would otherwise overwrite the terminal state with "running".
            monitor.stop()
            progress[key] = outcome
            _persist(db_factory, batch_id, progress=progress)
            if outcome["status"] == "failed":
                batch_failed = f"The '{key}' step failed: {outcome['message']}"
                break
            if outcome["status"] == "cancelled":
                cancelled = True
                for remaining in steps[index + 1:]:
                    progress[remaining["key"]] = {
                        "status": "cancelled",
                        "message": "Cancelled.",
                        "counts": None,
                    }
                break
        except Exception as exc:  # noqa: BLE001 - must not escape the task runner
            logger.exception("Batch step '%s' crashed", key)
            monitor.stop()  # freeze sampling before we write the failed state
            registry.finish(job, STATUS_FAILED, str(exc))
            progress[key] = {
                "status": "failed",
                "message": f"{type(exc).__name__}: {exc}",
                "counts": _counts(job),
            }
            batch_failed = f"The '{key}' step crashed: {type(exc).__name__}: {exc}"
            _persist(db_factory, batch_id, progress=progress)
            break
        finally:
            monitor.stop()
            with _active_lock:
                _active_jobs.pop(batch_id, None)

    if cancelled:
        _persist(
            db_factory, batch_id, progress=progress, status="cancelled",
            error=batch_failed, finish=True,
        )
    elif batch_failed:
        _persist(
            db_factory, batch_id, progress=progress, status="failed",
            error=batch_failed, finish=True,
        )
    else:
        _persist(
            db_factory, batch_id, progress=progress, status="completed", finish=True,
        )


def _load_records(db_factory: SessionFactory, record_ids: list[str]) -> list[ImageRecord]:
    """Reload the batch's records fresh for each step.

    Each step persists its own changes through its own session; a record held
    across steps would be a stale, detached copy whose writes silently clobber
    the step before it.
    """
    db = db_factory()
    try:
        records = (
            db.query(ImageRecord)
            .filter(ImageRecord.id.in_(record_ids))
            .order_by(ImageRecord.created_at)
            .all()
        )
        # Expunge so callers may mutate them without an open session; each
        # custom step re-merges its own record after writing.
        for record in records:
            db.expunge(record)
        return records
    finally:
        db.close()
