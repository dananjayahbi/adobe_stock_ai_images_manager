"""StepProgressMonitor: mid-step snapshots so the UI never sits on "Starting…"."""

from __future__ import annotations

import time

from services.jobs import Job, JobItem
from services.step_progress import StepProgressMonitor, live_message


def _job() -> Job:
    return Job(
        id="j1",
        stage="bg_remove",
        kind="batch-bg_remove",
        total=2,
        items=[
            JobItem(record_id="r1", filename="a.jpg"),
            JobItem(record_id="r2", filename="b.jpg"),
        ],
    )


def test_live_message_prefers_progress_label():
    job = _job()
    job.progress_label = "Upscaling · pass 1/2 · 40%"
    assert live_message(job, {"succeeded": 0}) == "Upscaling · pass 1/2 · 40%"


def test_live_message_uses_current_record_filename():
    job = _job()
    job.items[0].status = "running"
    assert live_message(job, {"succeeded": 0}) == "0/2 · a.jpg"


def test_live_message_falls_back_to_counts():
    job = _job()
    job.items[0].status = "succeeded"
    job.items[1].status = "failed"
    assert live_message(job, {"succeeded": 1, "failed": 1}) == "1 ok · 1 failed"


def test_monitor_publishes_and_stops():
    job = _job()
    job.items[0].status = "running"
    snaps: list[dict] = []
    monitor = StepProgressMonitor(
        job,
        snapshot=lambda msg, counts: {
            "status": "running",
            "message": msg,
            "counts": counts,
        },
        publish=snaps.append,
        interval=0.01,
    ).start()
    try:
        # First publish is synchronous in start().
        assert snaps and snaps[0]["message"] == "0/2 · a.jpg"  # pending -> current
        job.items[0].status = "succeeded"
        deadline = time.time() + 2.0
        while time.time() < deadline and not any(
            s["counts"]["succeeded"] == 1 for s in snaps
        ):
            time.sleep(0.01)
        assert any(s["counts"]["succeeded"] == 1 for s in snaps)
    finally:
        monitor.stop()
    # After stop no further snapshots arrive.
    count = len(snaps)
    time.sleep(0.05)
    assert len(snaps) == count


def test_monitor_drops_unchanged_snapshots():
    job = _job()
    snaps: list[dict] = []
    monitor = StepProgressMonitor(
        job,
        snapshot=lambda msg, counts: {"message": msg, "counts": counts},
        publish=snaps.append,
        interval=0.01,
    ).start()
    try:
        time.sleep(0.08)  # several ticks with no job change
    finally:
        monitor.stop()
    assert len(snaps) == 1
