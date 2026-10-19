"""Tests for the serial batch queue: enqueue, worker order, cancel, resume.

Fixture conventions follow ``conftest.py``: ``client`` (dependency-overridden
TestClient, background tasks run eagerly/synchronously) plus
``db_session_factory`` for direct DB access. ``queue_env`` points the worker's
session factory at the *test* database and stubs ``pipeline_runner.run_batch``
so no real step ever executes — the stub records execution order/concurrency
and writes the terminal state the real runner would.

The worker itself is the production code under test: the endpoint commits a
``queued`` row and kicks; ``services.batch_queue._worker`` claims, flips to
``running``, runs, and loops until the queue is empty.
"""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta

import pytest
from fastapi import BackgroundTasks

from main import app
from models import Batch, utcnow
from routers import batches as batches_router
from services import batch_queue
from tests.test_batch_pipeline import _create_batch, _jpg_bytes

# Captured at import time: the conftest autouse fixture stubs
# ``batch_queue.resume_on_boot`` for the lifespan (so a leftover queued row in
# the developer's real database never runs during a test), and this reference
# predates that patch — the restart test drives the REAL function with the
# test factory.
real_resume_on_boot = batch_queue.resume_on_boot


@pytest.fixture()
def queue_env(client, db_session_factory, monkeypatch):
    """A recording, order-preserving stand-in for the pipeline runner.

    Also asserts the worker flag starts clean so a wedged single-flight from
    an earlier test fails here with a clear message instead of silently
    skipping every queue test.
    """
    assert not batch_queue.is_active(), "serial worker flag leaked from a previous test"

    app.dependency_overrides[batches_router.get_batch_session_factory] = (
        lambda: db_session_factory
    )

    class QueueEnv:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.max_active = 0
            self.delay = 0.0

    env = QueueEnv()
    state = {"active": 0}

    def fake_run_batch(db_factory, batch_id, settings=None):
        state["active"] += 1
        env.max_active = max(env.max_active, state["active"])
        try:
            env.calls.append(batch_id)
            if env.delay:
                time.sleep(env.delay)
            db = db_factory()
            try:
                row = db.get(Batch, batch_id)
                # Mirror the real runner's terminal write (an operator cancel
                # wins: _persist never overwrites 'cancelled').
                if row is not None and row.status != "cancelled":
                    row.status = "completed"
                    row.finished_at = utcnow()
                    db.commit()
            finally:
                db.close()
        finally:
            state["active"] -= 1

    monkeypatch.setattr(batch_queue.pipeline_runner, "run_batch", fake_run_batch)
    yield env
    app.dependency_overrides.pop(
        batches_router.get_batch_session_factory, None
    )
    # A test that kicked without draining would wedge every later queue test
    # behind the setup assert; no worker threads survive the eager TestClient
    # (or an asyncio.run drain), so releasing the flag here only contains the
    # blast radius — each test's own assertions still catch real leaks.
    with batch_queue._lock:
        batch_queue._worker_active = False


def _ready_batch(client, name: str = "Batch") -> str:
    """A draft batch with one image — passes every enqueue precondition."""
    batch = _create_batch(client, name=name, steps=[{"key": "ocr"}])
    response = client.post(
        f"/api/batches/{batch['id']}/files",
        files=[("files", ("a.jpg", _jpg_bytes(), "image/jpeg"))],
    )
    assert response.status_code == 200, response.text
    return batch["id"]


def _set_status(db_session_factory, batch_id: str, status: str, **fields) -> None:
    db = db_session_factory()
    try:
        row = db.get(Batch, batch_id)
        row.status = status
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def _get_row(db_session_factory, batch_id: str) -> Batch:
    db = db_session_factory()
    try:
        row = db.get(Batch, batch_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def _drain(db_session_factory) -> None:
    """Kick and run one worker pass synchronously (boot-resume's building block)."""
    tasks = BackgroundTasks()
    assert batch_queue.kick(tasks, db_session_factory) is True
    asyncio.run(tasks())


# --------------------------------------------------------------------------- #
# Enqueue prechecks (409s mirror the original /run contract)
# --------------------------------------------------------------------------- #

class TestQueuePreconditions:
    def test_queue_without_images_is_409(self, client, queue_env):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(f"/api/batches/{batch['id']}/queue")
        assert response.status_code == 409
        assert "image" in response.json()["detail"].lower()
        # The precheck rejected before any kick: still a draft, worker idle.
        assert client.get(f"/api/batches/{batch['id']}").json()["status"] == "draft"
        assert queue_env.calls == []

    def test_queue_without_steps_is_409(self, client, db_session_factory, queue_env):
        batch_id = _ready_batch(client)
        db = db_session_factory()
        db.get(Batch, batch_id).steps = []
        db.commit()
        db.close()

        response = client.post(f"/api/batches/{batch_id}/queue")
        assert response.status_code == 409
        assert "step" in response.json()["detail"].lower()
        assert queue_env.calls == []

    def test_queue_on_running_is_409(self, client, db_session_factory, queue_env):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "running")

        response = client.post(f"/api/batches/{batch_id}/queue")
        assert response.status_code == 409
        assert "already running" in response.json()["detail"]
        assert _get_row(db_session_factory, batch_id).status == "running"
        assert queue_env.calls == []

    def test_queue_on_queued_is_409(self, client, db_session_factory, queue_env):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())

        response = client.post(f"/api/batches/{batch_id}/queue")
        assert response.status_code == 409
        assert "already queued" in response.json()["detail"]
        assert queue_env.calls == []

    def test_run_on_queued_is_409(self, client, db_session_factory, queue_env):
        """The compat /run path shares the prechecks with /queue."""
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())

        response = client.post(f"/api/batches/{batch_id}/run")
        assert response.status_code == 409
        assert "already queued" in response.json()["detail"]

    def test_completed_batch_is_rejected_on_both_paths(
        self, client, db_session_factory, queue_env
    ):
        """A processed batch is terminal: rerun requires a fresh batch."""
        batch_id = _ready_batch(client)
        _set_status(
            db_session_factory, batch_id, "completed", finished_at=utcnow()
        )

        for path in ("run", "queue"):
            response = client.post(f"/api/batches/{batch_id}/{path}")
            assert response.status_code == 409, response.text
            detail = response.json()["detail"]
            assert "processed" in detail
            assert "delete" in detail

        # Refused before any state change or worker kick.
        assert _get_row(db_session_factory, batch_id).status == "completed"
        assert queue_env.calls == []

    def test_cancelled_batch_can_be_reenqueued(
        self, client, db_session_factory, queue_env
    ):
        """Only `completed` is ban-from-rerun; a cancelled batch is runnable."""
        batch_id = _ready_batch(client)
        _set_status(
            db_session_factory, batch_id, "cancelled", finished_at=utcnow()
        )

        response = client.post(f"/api/batches/{batch_id}/run")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "queued"
        assert queue_env.calls == [batch_id]


# --------------------------------------------------------------------------- #
# Enqueue semantics
# --------------------------------------------------------------------------- #

class TestQueueEnqueue:
    def test_queue_sets_queued_and_stamps_queued_at(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)

        response = client.post(f"/api/batches/{batch_id}/queue")
        assert response.status_code == 200, response.text
        body = response.json()
        # The response is serialized before background tasks run, so it shows
        # the queued state even though the eager TestClient worker finishes
        # before client.post() returns.
        assert body["status"] == "queued"
        assert body["queued_at"] is not None
        assert body["error"] is None
        assert body["finished_at"] is None

        # The worker drained it (stubbed runner wrote 'completed').
        assert queue_env.calls == [batch_id]
        assert client.get(f"/api/batches/{batch_id}").json()["status"] == "completed"
        assert not batch_queue.is_active()

    def test_run_endpoint_now_enqueues_instead_of_running(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)

        response = client.post(f"/api/batches/{batch_id}/run")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "queued"
        assert response.json()["queued_at"] is not None

        assert queue_env.calls == [batch_id]
        assert client.get(f"/api/batches/{batch_id}").json()["status"] == "completed"

    def test_enqueue_clears_a_previous_error_and_finish(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)
        _set_status(
            db_session_factory,
            batch_id,
            "failed",
            error="The 'ocr' step failed: boom",
            finished_at=utcnow(),
        )

        body = client.post(f"/api/batches/{batch_id}/queue").json()
        assert body["status"] == "queued"
        assert body["error"] is None
        assert body["finished_at"] is None

    def test_draft_batch_reports_a_null_queued_at(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        fetched = client.get(f"/api/batches/{batch['id']}").json()
        assert fetched["queued_at"] is None

    def test_list_response_carries_queued_at(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)
        client.post(f"/api/batches/{batch_id}/queue")

        items = client.get("/api/batches").json()["items"]
        item = next(i for i in items if i["id"] == batch_id)
        assert item["queued_at"] is not None


# --------------------------------------------------------------------------- #
# The serial worker
# --------------------------------------------------------------------------- #

class TestSerialWorker:
    def test_worker_runs_queued_batches_in_queued_at_order(
        self, client, db_session_factory, queue_env
    ):
        """Three queued rows, one worker, execution order = queued_at order."""
        first = _ready_batch(client, "First created")
        second = _ready_batch(client, "Second created")
        third = _ready_batch(client, "Third created")

        # Fixed base + whole seconds: deliberately NOT creation order —
        # `third` was queued first, `second` last — so the claim order must
        # come from queued_at, not id/insertion order.
        base = utcnow() - timedelta(seconds=5)
        _set_status(db_session_factory, third, "queued", queued_at=base)
        _set_status(
            db_session_factory, first, "queued", queued_at=base + timedelta(seconds=1)
        )
        _set_status(
            db_session_factory, second, "queued", queued_at=base + timedelta(seconds=2)
        )

        queue_env.delay = 0.02  # widen the overlap window if single-flight broke
        _drain(db_session_factory)

        assert queue_env.calls == [third, first, second]
        assert queue_env.max_active == 1
        for batch_id in (third, first, second):
            assert _get_row(db_session_factory, batch_id).status == "completed"

    def test_kick_is_single_flight(self, client, db_session_factory, queue_env):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())

        tasks = BackgroundTasks()
        assert batch_queue.kick(tasks, db_session_factory) is True
        # Second kick while the first is still scheduled: refused, no task.
        assert batch_queue.kick(tasks, db_session_factory) is False
        assert len(tasks.tasks) == 1
        assert batch_queue.is_active()

        asyncio.run(tasks())
        assert queue_env.calls == [batch_id]
        # The flag is released when the queue drains, so a later kick works.
        assert not batch_queue.is_active()
        again = BackgroundTasks()
        assert batch_queue.kick(again, db_session_factory) is True
        asyncio.run(again())  # empty queue: the worker exits and frees the flag
        assert not batch_queue.is_active()

    def test_kick_after_drain_schedules_a_fresh_worker(
        self, client, db_session_factory, queue_env
    ):
        """A queue that emptied re-opens: kick succeeds and runs the new row."""
        first = _ready_batch(client, "One")
        _set_status(db_session_factory, first, "queued", queued_at=utcnow())
        _drain(db_session_factory)
        assert not batch_queue.is_active()

        second = _ready_batch(client, "Two")
        _set_status(db_session_factory, second, "queued", queued_at=utcnow())
        _drain(db_session_factory)

        assert queue_env.calls == [first, second]

    def test_cancelled_rows_are_never_claimed(
        self, client, db_session_factory, queue_env
    ):
        cancelled = _ready_batch(client, "Cancelled")
        queued = _ready_batch(client, "Queued")
        _set_status(
            db_session_factory, cancelled, "cancelled", finished_at=utcnow()
        )
        _set_status(db_session_factory, queued, "queued", queued_at=utcnow())

        _drain(db_session_factory)

        assert queue_env.calls == [queued]
        assert _get_row(db_session_factory, cancelled).status == "cancelled"

    def test_concurrent_api_enqueues_stay_serial(
        self, client, db_session_factory, queue_env
    ):
        """What clients do today: several POSTs back to back, one at a time."""
        ids = [_ready_batch(client, f"Batch {i}") for i in range(3)]
        queue_env.delay = 0.01

        responses = [client.post(f"/api/batches/{bid}/run") for bid in ids]

        assert [r.status_code for r in responses] == [200, 200, 200]
        assert all(r.json()["status"] == "queued" for r in responses)
        assert queue_env.calls == ids  # creation order == queued_at order
        assert queue_env.max_active == 1
        assert not batch_queue.is_active()


# --------------------------------------------------------------------------- #
# Cancel
# --------------------------------------------------------------------------- #

class TestCancelFromQueued:
    def test_cancel_a_queued_batch_flips_status_and_finishes(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())

        response = client.post(f"/api/batches/{batch_id}/cancel")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "cancelled"
        assert body["finished_at"] is not None

    def test_worker_skips_the_cancelled_row_after_the_flip(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())
        client.post(f"/api/batches/{batch_id}/cancel")

        _drain(db_session_factory)

        assert queue_env.calls == []
        assert _get_row(db_session_factory, batch_id).status == "cancelled"
        assert not batch_queue.is_active()

    def test_cancel_still_refuses_a_draft(self, client, queue_env):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        assert client.post(f"/api/batches/{batch['id']}/cancel").status_code == 409


# --------------------------------------------------------------------------- #
# Restart: queued rows survive, boot kick drains them
# --------------------------------------------------------------------------- #

class TestRestartResume:
    def test_queued_rows_survive_restart_and_the_boot_kick_runs_them(
        self, client, db_session_factory, queue_env
    ):
        queued_id = _ready_batch(client, "Survives")
        running_id = _ready_batch(client, "Interrupted")
        _set_status(db_session_factory, queued_id, "queued", queued_at=utcnow())
        _set_status(db_session_factory, running_id, "running")

        # Simulated restart: the startup repair fails `running` rows only.
        session = db_session_factory()
        engine = session.get_bind()
        session.close()
        from services.pipeline_runner import recover_interrupted_batches

        assert recover_interrupted_batches(engine) == 1
        assert _get_row(db_session_factory, running_id).status == "failed"
        survivor = _get_row(db_session_factory, queued_id)
        assert survivor.status == "queued"
        assert survivor.queued_at is not None

        # Boot kick: the REAL resume (import-time capture), test factory.
        tasks = real_resume_on_boot(db_session_factory, None)
        assert tasks is not None, "boot resume must schedule a worker for queued rows"
        asyncio.run(tasks())

        assert queue_env.calls == [queued_id]
        assert _get_row(db_session_factory, queued_id).status == "completed"
        assert not batch_queue.is_active()

    def test_boot_resume_is_a_noop_when_the_queue_is_empty(
        self, client, db_session_factory, queue_env
    ):
        assert real_resume_on_boot(db_session_factory, None) is None
        assert not batch_queue.is_active()

    def test_boot_resume_is_idempotent_while_a_worker_is_active(
        self, client, db_session_factory, queue_env
    ):
        batch_id = _ready_batch(client)
        _set_status(db_session_factory, batch_id, "queued", queued_at=utcnow())

        first = BackgroundTasks()
        assert batch_queue.kick(first, db_session_factory) is True
        # A second boot-resume attempt while the worker is scheduled: nothing.
        assert real_resume_on_boot(db_session_factory, None) is None

        asyncio.run(first())
        assert queue_env.calls == [batch_id]
