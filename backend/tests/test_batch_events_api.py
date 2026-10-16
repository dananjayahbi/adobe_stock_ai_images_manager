"""Tests for the batch SSE endpoint (mobile M4 prerequisite B1, roadmap §3).

Frames reuse ``BatchResponse`` — the same model ``GET /api/batches/{id}``
serves (its detail response extends it) — so the mobile client parses one
shape whether it polls or streams. The stream opens its own database session
through a factory dependency (the research stream's pattern), so the autouse
fixture points it at the test database instead of the live one.
"""

from __future__ import annotations

import json

import pytest

from routers import batches as batches_router
from tests.test_batch_pipeline import _create_batch


@pytest.fixture(autouse=True)
def stream_session_factory(db_session_factory):
    """Point the streaming endpoint at the test database.

    The streamed body outlives the request's dependencies and opens its own
    session; without this override it would poll the real ``storage`` database,
    where the batch created below does not exist.
    """
    from main import app

    app.dependency_overrides[batches_router.get_batch_session_factory] = (
        lambda: db_session_factory
    )
    yield
    app.dependency_overrides.pop(batches_router.get_batch_session_factory, None)


def _batch_frames(body: str) -> list[dict]:
    """Parse the BatchResponse ``data:`` frames out of a raw SSE body.

    The terminal marker's ``data: {}`` carries no batch id, so it is filtered
    out here and asserted on separately.
    """
    payloads = [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    return [payload for payload in payloads if "id" in payload]


# --------------------------------------------------------------------------- #
# Auth — the global middleware covers the route; nothing special is done here
# --------------------------------------------------------------------------- #

def test_events_require_a_session_cookie(client, monkeypatch):
    """No cookie -> 401 before routing runs; the path is not allowlisted."""
    from auth_config import auth_settings

    monkeypatch.setattr(auth_settings, "AUTH_ENABLED", True)
    response = client.get("/api/batches/some-id/events")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


# --------------------------------------------------------------------------- #
# HTTP surface
# --------------------------------------------------------------------------- #

def test_unknown_batch_is_404_not_a_hung_stream(client):
    """A bad id fails up front with the router's usual 404 body."""
    response = client.get("/api/batches/no-such-batch/events")
    assert response.status_code == 404
    assert response.json() == {"detail": "Batch no-such-batch does not exist."}


def test_snapshot_progress_then_terminal_done(client, monkeypatch):
    """Initial snapshot, a frame per change, then done — and the stream ends.

    The progress source is a thin wrapper over the real DB fetch that flips
    the batch to ``running`` on the second read and ``completed`` on the
    third: framing, serialization, change detection, and the terminal close
    are all exercised for real, while the test stays deterministic and fast.
    """
    batch = _create_batch(client, steps=[{"key": "ocr"}])

    real_fetch = batches_router._current_batch_payload
    reads = {"n": 0}

    def flipping_fetch(session_factory, batch_id):
        reads["n"] += 1
        payload = real_fetch(session_factory, batch_id)
        if payload is None:
            return None
        if reads["n"] >= 3:
            payload.status = "completed"
            payload.finished_at = "2026-01-01T00:00:00+00:00"
        elif reads["n"] == 2:
            payload.status = "running"
            payload.step_progress = {
                "ocr": {"status": "running", "message": "", "counts": None}
            }
        return payload

    monkeypatch.setattr(batches_router, "_current_batch_payload", flipping_fetch)
    # Poll fast so the whole stream closes in well under a second.
    monkeypatch.setattr(batches_router, "_BATCH_POLL_SECONDS", 0.02)

    with client.stream("GET", f"/api/batches/{batch['id']}/events") as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["x-accel-buffering"] == "no"
        assert "no-cache" in response.headers["cache-control"]
        # Blocks until the terminal frame and done marker close the stream.
        body = "".join(response.iter_text())

    frames = _batch_frames(body)
    assert len(frames) == 3

    # The snapshot arrives immediately, before any change: it round-trips
    # through BatchResponse and matches GET /api/batches/{id}'s serialization.
    snapshot = batches_router.BatchResponse.model_validate(frames[0])
    assert snapshot.id == batch["id"]
    assert snapshot.status == "draft"
    assert set(frames[0]) == set(batches_router.BatchResponse.model_fields)

    # The progress change is pushed as its own frame...
    assert frames[1]["id"] == batch["id"]
    assert frames[1]["status"] == "running"
    assert frames[1]["step_progress"]["ocr"]["status"] == "running"

    # ...then the terminal frame, then research-style done closes the stream.
    assert frames[2]["status"] == "completed"
    assert frames[2]["finished_at"] is not None
    assert body.rstrip().endswith("event: done\ndata: {}")
