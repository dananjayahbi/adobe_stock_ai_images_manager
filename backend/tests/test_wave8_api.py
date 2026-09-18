from datetime import datetime, timezone

import pytest

from app.api import (
    ApiError,
    CursorPage,
    IdempotencyStore,
    JobSnapshot,
    SessionManager,
    create_error,
    paginate,
    safe_asset_response,
    validate_action,
)


def test_cursor_pagination_is_bounded_and_deterministic():
    records = [{"id": f"asset-{index}", "updated_at": "2026-01-01T00:00:00+00:00"} for index in range(5)]
    page = paginate(records, limit=2)
    assert isinstance(page, CursorPage)
    assert [item["id"] for item in page.items] == ["asset-0", "asset-1"]
    assert page.next_cursor == "asset-1"
    assert [item["id"] for item in paginate(records, limit=2, cursor=page.next_cursor).items] == ["asset-2", "asset-3"]
    with pytest.raises(ApiError):
        paginate(records, limit=501)


def test_action_requires_revision_and_idempotency_key():
    validate_action(expected_revision=3, idempotency_key="key-1", actor="operator")
    with pytest.raises(ApiError, match="revision"):
        validate_action(expected_revision=None, idempotency_key="key-1", actor="operator")
    with pytest.raises(ApiError, match="idempotency"):
        validate_action(expected_revision=3, idempotency_key="", actor="operator")


def test_idempotency_replays_original_result_and_rejects_conflicting_payload():
    store = IdempotencyStore()
    first = store.record("key-1", {"action": "approve"}, {"job_id": "job-1"})
    assert first == store.replay("key-1", {"action": "approve"})
    with pytest.raises(ApiError, match="different"):
        store.replay("key-1", {"action": "reject"})


def test_session_is_local_and_expiry_is_explicit():
    sessions = SessionManager(ttl_seconds=60)
    session = sessions.create("operator")
    assert sessions.get(session.session_id).actor == "operator"
    sessions.expire(session.session_id)
    with pytest.raises(ApiError, match="session"):
        sessions.get(session.session_id)


def test_safe_response_omits_paths_secrets_and_unbounded_evidence():
    response = safe_asset_response(
        {"id": "asset-1", "status": "READY", "version": 2, "source_path": "C:/secret/image.jpg", "api_key": "secret", "findings": list(range(100))}
    )
    assert response == {"id": "asset-1", "status": "READY", "version": 2, "findings": []}


def test_job_snapshot_exposes_stage_counters_and_safe_error():
    snapshot = JobSnapshot("job-1", "asset-1", "semantic_audit", "RUNNING", "semantic", 1, 3, 0, 0, None)
    assert snapshot.to_dict()["progress"] == {"completed": 1, "total": 3, "failed": 0, "blocked": 0}
    error = create_error("validation", "bad-input", "Invalid upload", correlation_id="corr-1")
    assert error == {"type": "validation", "code": "bad-input", "message": "Invalid upload", "correlation_id": "corr-1"}
