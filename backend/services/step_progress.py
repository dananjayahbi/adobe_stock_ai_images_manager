"""Live step-progress reporting for the batch pipeline.

A step can run for minutes (model load, per-record inference), but the runner
used to write ``step_progress`` only once at step start (``"Starting…"``) and
once at the end — so the UI sat on "Starting…" for the whole step and looked
hung. This monitor samples the in-flight :class:`~services.jobs.Job` while the
step runs and pushes a fresh ``{status, message, counts}`` snapshot to a
callback, so the processing page shows real counts as records complete.

Kept out of ``pipeline_runner`` on purpose: the runner is already dense, and
this is independently testable (drive a Job by hand, assert the snapshots).
"""

from __future__ import annotations

import threading
from typing import Callable

from services.jobs import Job

#: How often to sample the job, in seconds.
DEFAULT_INTERVAL = 1.0


def live_message(job: Job, counts: dict) -> str:
    """Human-readable line for a mid-step snapshot.

    Prefers a per-record label (upscale streams "pass 1/2 · 40%"), then the
    current record's filename, then the plain counts — whatever says the most
    about what is happening right now.
    """
    if job.progress_label:
        return job.progress_label
    current = job.current
    if current is not None:
        detail = current.detail or current.message or current.filename
        return f"{counts.get('succeeded', 0)}/{job.total} · {detail}"
    parts = [f"{counts.get('succeeded', 0)} ok"]
    if counts.get("failed"):
        parts.append(f"{counts['failed']} failed")
    if counts.get("skipped"):
        parts.append(f"{counts['skipped']} skipped")
    return " · ".join(parts)


class StepProgressMonitor:
    """Poll a running job and publish progress snapshots until stopped.

    ``snapshot`` builds the full progress dict for the step; ``publish`` hands
    it to the caller (which persists it). Snapshots that are unchanged since
    the last publish are dropped, so an idle step does not hammer SQLite.
    """

    def __init__(
        self,
        job: Job,
        snapshot: Callable[[str, dict], dict],
        publish: Callable[[dict], None],
        *,
        interval: float = DEFAULT_INTERVAL,
    ) -> None:
        self._job = job
        self._snapshot = snapshot
        self._publish = publish
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: tuple[str, tuple] | None = None

    def _tick(self) -> None:
        counts = {
            "succeeded": 0,
            "failed": 0,
            "skipped": 0,
            "pending": 0,
        }
        for item in self._job.items:
            counts[item.status] = counts.get(item.status, 0) + 1
        message = live_message(self._job, counts)
        key = (message, tuple(sorted(counts.items())))
        if key == self._last:  # nothing changed — don't write again
            return
        self._last = key
        self._publish(self._snapshot(message, counts))

    def _run(self) -> None:
        # Publish once immediately so the UI leaves "Starting…" as soon as the
        # step actually begins, not one interval later.
        while not self._stop.wait(self._interval):
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - progress must never kill a step
                return
        # Final tick on the way out so the last counts are never a stale frame.
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            pass

    def start(self) -> "StepProgressMonitor":
        self._tick()
        self._thread = threading.Thread(
            target=self._run, name="step-progress", daemon=True
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
