"""In-process job tracking for long-running stage batches.

Stage 3-6 batches call external tools (Upscayl, the LLM gateway) that can take
minutes per image. The operator needs live progress rather than a request that
hangs until the whole batch finishes, so batches run as background tasks and
report progress through this registry.

This is intentionally process-local: the app is a single-user local tool, and a
job's useful lifetime ends when the process does.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: Terminal job states.
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

#: Jobs are kept in memory only long enough for the UI to read the result.
MAX_RETAINED_JOBS = 40


@dataclass
class JobItem:
    """Per-record progress inside a batch."""

    record_id: str
    filename: str
    status: str = "pending"  # pending | running | succeeded | failed | skipped
    message: str = ""
    score: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    #: 0-100 progress *within this record*, for stages slow enough to report it.
    #: Upscaling is the main consumer: the CLI streams a percentage per image,
    #: so the UI can show a real bar instead of a spinner. None means the stage
    #: cannot report intra-record progress.
    progress: float | None = None
    #: Short human-readable phase label, e.g. "Upscaling · pass 1/2 · 40%".
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "filename": self.filename,
            "status": self.status,
            "message": self.message,
            "score": self.score,
            "progress": round(self.progress, 1) if self.progress is not None else None,
            "detail": self.detail,
            "duration_seconds": (
                round(self.finished_at - self.started_at, 2)
                if self.started_at and self.finished_at
                else None
            ),
        }


@dataclass
class Job:
    """A tracked batch operation."""

    id: str
    stage: str
    kind: str
    total: int
    status: str = STATUS_RUNNING
    items: list[JobItem] = field(default_factory=list)
    message: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    #: Cooperative cancellation flag, checked between records.
    cancel_requested: bool = False
    #: Free-text description of what the batch is doing right now, shown beside
    #: the progress bar (e.g. "Upscaling 4K with 4xNomos8kSC on GPU 0").
    progress_label: str = ""

    @property
    def processed(self) -> int:
        return sum(
            1 for item in self.items if item.status in ("succeeded", "failed", "skipped")
        )

    @property
    def current(self) -> JobItem | None:
        """The item currently running, if any."""
        for item in self.items:
            if item.status == "running":
                return item
        return None

    def report_progress(
        self, record_id: str, percent: float, label: str = ""
    ) -> None:
        """Update one item's intra-record progress.

        Called from the worker thread, so it is deliberately limited to plain
        attribute assignment: this is a single-user local tool, and the poller
        reading a slightly stale number is harmless.
        """
        for item in self.items:
            if item.record_id == record_id:
                item.progress = max(0.0, min(100.0, float(percent)))
                if label:
                    item.detail = label
                return

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.items if item.status == "succeeded")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.items if item.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.items if item.status == "skipped")

    @property
    def progress(self) -> float:
        """Overall completion in 0-1, including the running record's own progress.

        Counting only finished records makes the bar sit still for minutes
        during a single large upscale, which reads as a hang. Weighting the
        running record by its reported percentage keeps the bar honest.
        """
        if self.total <= 0:
            return 1.0 if self.status != STATUS_RUNNING else 0.0

        partial = sum(
            (item.progress or 0.0) / 100.0
            for item in self.items
            if item.status == "running"
        )
        return round(min(1.0, (self.processed + partial) / self.total), 4)

    def to_dict(self, include_items: bool = True) -> dict:
        payload = {
            "id": self.id,
            "stage": self.stage,
            "kind": self.kind,
            "status": self.status,
            "message": self.message,
            "progress_label": self.progress_label,
            "total": self.total,
            "processed": self.processed,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "progress": self.progress,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "duration_seconds": (
                round((self.finished_at or time.time()) - self.created_at, 2)
            ),
        }
        current = self.current
        payload["current_record_id"] = current.record_id if current else None
        if include_items:
            payload["items"] = [item.to_dict() for item in self.items]
        return payload


class JobRegistry:
    """Thread-safe store of active and recently finished jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, stage: str, kind: str, items: list[JobItem]) -> Job:
        """Register a new running job for the given items."""
        job = Job(
            id=uuid.uuid4().hex,
            stage=stage,
            kind=kind,
            total=len(items),
            items=items,
        )
        with self._lock:
            self._jobs[job.id] = job
            self._evict_locked()
        logger.info("Started %s job %s for %d record(s)", kind, job.id, job.total)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_recent(self, limit: int = 10) -> list[Job]:
        """Most recent jobs first."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(), key=lambda job: job.created_at, reverse=True
            )
        return jobs[:limit]

    def cancel(self, job_id: str) -> bool:
        """Request cooperative cancellation of a running job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != STATUS_RUNNING:
                return False
            job.cancel_requested = True
        logger.info("Cancellation requested for job %s", job_id)
        return True

    def finish(self, job: Job, status: str, message: str = "") -> None:
        """Mark a job terminal.

        An empty ``message`` preserves whatever the runner already set (for
        example "3 record(s) not found"), so completion never erases context the
        operator needs.
        """
        with self._lock:
            job.status = status
            if message:
                job.message = message
            job.finished_at = time.time()
        logger.info("Job %s finished with status %s", job.id, status)

    def _evict_locked(self) -> None:
        """Drop the oldest finished jobs once the retention cap is exceeded."""
        if len(self._jobs) <= MAX_RETAINED_JOBS:
            return

        finished = sorted(
            (job for job in self._jobs.values() if job.status != STATUS_RUNNING),
            key=lambda job: job.finished_at or job.created_at,
        )
        for job in finished[: len(self._jobs) - MAX_RETAINED_JOBS]:
            self._jobs.pop(job.id, None)


#: Process-wide registry shared by the routers and the orchestrator.
registry = JobRegistry()
