"""Serial batch queue - one batch at a time, in queued order.

The API used to dispatch ``pipeline_runner.run_batch`` immediately, so every
"run" clicked in the same moment raced its own background thread and batches
ran concurrently across ids. The queue gives the app a single ordering:

* ``POST /api/batches/{id}/queue`` (and ``/run``, which is now an alias for
  it) stamps ``status='queued'`` + ``queued_at`` and calls :func:`kick`.
* One module-level worker claims rows ``status='queued' ORDER BY queued_at
  ASC, batch_id ASC`` and runs each to a terminal state before the next
  claim. ``pipeline_runner.run_batch`` writes the terminal statuses itself.

Single-flight is a module-level ``threading.Lock`` + ``_worker_active`` flag
(the ``services.jobs.JobRegistry`` pattern): :func:`kick` check-and-sets the
flag under the lock, so N simultaneous requests schedule exactly one worker
task. The worker deactivates *atomically with the empty claim* — there is no
window where a row queued between "queue empty" and "flag cleared" could be
missed — and a ``finally`` clears the flag on every other path out.

Queued rows survive a restart by design (only ``running`` rows are failed by
``recover_interrupted_batches``); :func:`resume_on_boot` schedules the worker
again from the lifespan.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from config import Settings
from models import Batch
from services import pipeline_runner

SessionFactory = Callable[[], Session]

logger = logging.getLogger(__name__)

#: Guards ``_worker_active`` and every claim. One lock (not one per concern)
#: keeps the check-and-set in :func:`kick` and the claim/deactivate pair in
#: :func:`_worker` mutually exclusive, which is what makes single-flight hold.
_lock = threading.Lock()

#: True from the moment a worker is scheduled until it exits. Set by
#: :func:`kick` (under the lock) so a second kick cannot double-schedule.
_worker_active = False


def is_active() -> bool:
    """True while a worker is scheduled or running (diagnostics/tests)."""
    with _lock:
        return _worker_active


def kick(background_tasks: BackgroundTasks, db_factory: SessionFactory, settings: Settings | None = None) -> bool:
    """Schedule the serial worker unless one is already scheduled/running.

    Returns True when this call won the race and added the task. The caller
    commits its ``queued`` row *before* kicking, so a worker that is mid-run
    picks the new row up on its next claim and a worker that is about to exit
    sees it during its final claim.
    """
    global _worker_active
    with _lock:
        if _worker_active:
            return False
        _worker_active = True
    background_tasks.add_task(_worker, db_factory, settings)
    return True


def _claim_next(db_factory: SessionFactory) -> str | None:
    """Oldest queued batch, flipped to ``running``; None when the queue is empty.

    Callers hold ``_lock``: the claim and the ``running`` flip happen as one
    critical section so two workers can never take the same row (and the
    "queue empty" answer cannot interleave with another kick's check).
    """
    db = db_factory()
    try:
        batch = (
            db.query(Batch)
            .filter(Batch.status == "queued")
            .order_by(Batch.queued_at.asc(), Batch.id.asc())
            .first()
        )
        if batch is None:
            return None
        batch.status = "running"
        db.commit()
        return batch.id
    finally:
        db.close()


def _worker(db_factory: SessionFactory, settings: Settings | None = None) -> None:
    """Drain the queue serially. Never raises; ``finally`` frees the flag."""
    global _worker_active
    try:
        while True:
            try:
                with _lock:
                    batch_id = _claim_next(db_factory)
                    if batch_id is None:
                        # Deactivate *inside* the claim's critical section: a
                        # kick waiting on the lock then schedules a fresh
                        # worker instead of being told "already running" by a
                        # flag that is about to drop.
                        _worker_active = False
                        return
            except Exception:  # noqa: BLE001 - leave rows queued, free the flag
                logger.exception("Serial queue: claim failed; worker exiting")
                return
            try:
                # Sync on purpose: the worker itself runs in a threadpool via
                # BackgroundTasks, and the next claim must wait for this run.
                pipeline_runner.run_batch(db_factory, batch_id, settings)
            except Exception:  # noqa: BLE001 - a poison row must not kill the loop
                logger.exception("Serial queue: run_batch crashed for %s", batch_id)
    finally:
        with _lock:
            _worker_active = False


def has_queued(db_factory: SessionFactory) -> bool:
    """True when at least one batch is waiting in the queue."""
    db = db_factory()
    try:
        return db.query(Batch.id).filter(Batch.status == "queued").first() is not None
    finally:
        db.close()


def resume_on_boot(db_factory: SessionFactory, settings: Settings | None = None) -> BackgroundTasks | None:
    """Schedule the worker if queued rows survived a restart; None otherwise.

    Called from the lifespan after ``recover_interrupted_batches`` (which
    fails ``running`` rows only — ``queued`` rows are durable on purpose). The
    returned ``BackgroundTasks`` has the worker task added but *not run*: the
    lifespan fires it on its own event loop so startup never blocks on a long
    queue. Idempotent: a worker already active makes this a no-op.
    """
    if not has_queued(db_factory):
        return None
    tasks = BackgroundTasks()
    if not kick(tasks, db_factory, settings):
        return None
    return tasks
