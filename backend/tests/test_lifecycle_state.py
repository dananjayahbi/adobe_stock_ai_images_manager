"""Tests for the lifecycle state axis: column, flags, transitions, endpoints.

The ``state`` column is the single coordinate the publish/download/export flow
reads; ``flags`` are derived at serialization and never stored. These tests pin
the contract: the PATCH whitelist, the fast (LLM-free) approve path, the used→
published push, flag derivation order, the migration backfill mapping, and the
``?state=`` filter + ``state_counts`` summary.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from models import ImageLifecycleState, ImageRecord, ImageStatus, PipelineStage
from services.image_lifecycle import compute_flags, refresh_state_for_stage
from tests.test_stage_pipeline import pipeline_env  # noqa: F401  (shared fixture)

ALL_STATES = {state.value for state in ImageLifecycleState}


def _seed(db_session_factory, **overrides) -> str:
    """Insert a record directly and return its id."""
    session = db_session_factory()
    try:
        record = ImageRecord(
            filename=overrides.pop("filename", "asset.jpg"),
            original_path=overrides.pop("original_path", "/tmp/asset.jpg"),
            file_size_bytes=overrides.pop("file_size_bytes", 1024),
            **overrides,
        )
        session.add(record)
        session.commit()
        return record.id
    finally:
        session.close()


def _reload(db_session_factory, record_id: str) -> ImageRecord:
    session = db_session_factory()
    try:
        record = session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
        assert record is not None
        session.expunge(record)
        return record
    finally:
        session.close()


def _transient(**overrides) -> ImageRecord:
    """An unsaved record with explicit values for everything flags read."""
    defaults = dict(
        filename="asset.jpg",
        original_path="/tmp/asset.jpg",
        file_size_bytes=1024,
    )
    defaults.update(overrides)
    return ImageRecord(**defaults)


# --------------------------------------------------------------------------- #
# 1. PATCH /api/records/{id}/state — whitelist
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("APPROVED", "READY_TO_PUBLISH"),
        ("REJECTED", "READY_TO_PUBLISH"),
        ("READY_TO_PUBLISH", "APPROVED"),
        ("PUBLISHED", "AS_ACCEPTED"),
        ("AS_ACCEPTED", "PUBLISHED"),
        ("REJECTED", "APPROVED"),
    ],
)
def test_state_endpoint_allows_whitelisted_transitions(
    client, db_session_factory, from_state, to_state
):
    record_id = _seed(
        db_session_factory, state=ImageLifecycleState(from_state)
    )

    response = client.patch(
        f"/api/records/{record_id}/state", json={"state": to_state}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    # Full RecordResponse, not just the state.
    assert body["id"] == record_id
    assert body["state"] == to_state
    assert isinstance(body["flags"], list)
    assert _reload(db_session_factory, record_id).state == ImageLifecycleState(to_state)


@pytest.mark.parametrize(
    ("from_state", "to_state"),
    [
        ("COLLECTED", "APPROVED"),
        ("APPROVED", "PUBLISHED"),
        ("APPROVED", "AS_ACCEPTED"),
        ("READY_TO_PUBLISH", "REJECTED"),
        ("PUBLISHED", "READY_TO_PUBLISH"),
        # Same-state moves are not whitelisted either.
        ("APPROVED", "APPROVED"),
    ],
)
def test_state_endpoint_rejects_disallowed_transitions(
    client, db_session_factory, from_state, to_state
):
    record_id = _seed(
        db_session_factory, state=ImageLifecycleState(from_state)
    )

    response = client.patch(
        f"/api/records/{record_id}/state", json={"state": to_state}
    )

    assert response.status_code == 400
    assert from_state in response.json()["detail"]
    assert _reload(db_session_factory, record_id).state == ImageLifecycleState(from_state)


def test_state_endpoint_rejects_unknown_value_with_accepted_list(
    client, db_session_factory
):
    record_id = _seed(db_session_factory, state=ImageLifecycleState.APPROVED)

    response = client.patch(
        f"/api/records/{record_id}/state", json={"state": "NOT_A_STATE"}
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Invalid state" in detail
    assert "Accepted values" in detail
    for value in ALL_STATES:
        assert value in detail
    assert _reload(db_session_factory, record_id).state == ImageLifecycleState.APPROVED


def test_state_endpoint_404s_for_missing_record(client):
    response = client.patch(
        "/api/records/nope/state", json={"state": "APPROVED"}
    )
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# 2. POST /api/records/{id}/approve — fast path, no LLM
# --------------------------------------------------------------------------- #

def test_approve_flips_approved_to_ready_to_publish(client, db_session_factory):
    record_id = _seed(
        db_session_factory,
        state=ImageLifecycleState.APPROVED,
        status=ImageStatus.PASSED,
        generated_title="A Title",
        generated_keywords=["a", "b", "c"],
    )

    response = client.post(f"/api/records/{record_id}/approve")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["record_id"] == record_id
    assert body["state"] == "READY_TO_PUBLISH"
    assert body["title"] == "A Title"
    assert body["keywords_count"] == 3
    assert _reload(db_session_factory, record_id).state == (
        ImageLifecycleState.READY_TO_PUBLISH
    )


def test_approve_flips_rejected_to_ready_to_publish(client, db_session_factory):
    record_id = _seed(
        db_session_factory, state=ImageLifecycleState.REJECTED
    )

    response = client.post(f"/api/records/{record_id}/approve")

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "READY_TO_PUBLISH"


def test_approve_makes_no_llm_or_pipeline_calls(
    client, db_session_factory, monkeypatch
):
    """The >10s bug: approve must never reach the approval pipeline."""
    from tasks import audit_orchestrator

    def _boom(*args, **kwargs):
        pytest.fail("approve must not run the approval pipeline / LLM")

    monkeypatch.setattr(audit_orchestrator, "process_approval", _boom)
    monkeypatch.setattr(audit_orchestrator.gemini_metadata, "generate_metadata", _boom)

    record_id = _seed(db_session_factory, state=ImageLifecycleState.APPROVED)

    response = client.post(f"/api/records/{record_id}/approve")

    assert response.status_code == 200
    assert response.json()["state"] == "READY_TO_PUBLISH"


@pytest.mark.parametrize("already", ["READY_TO_PUBLISH", "PUBLISHED", "AS_ACCEPTED"])
def test_approve_is_idempotent_for_queued_or_later_states(
    client, db_session_factory, already
):
    record_id = _seed(db_session_factory, state=ImageLifecycleState(already))

    response = client.post(f"/api/records/{record_id}/approve")

    assert response.status_code == 200
    assert response.json()["state"] == already
    assert _reload(db_session_factory, record_id).state == ImageLifecycleState(already)


def test_approve_rejects_unprocessed_record(client, db_session_factory):
    record_id = _seed(db_session_factory, state=ImageLifecycleState.COLLECTED)

    response = client.post(f"/api/records/{record_id}/approve")

    assert response.status_code == 400
    assert "COLLECTED" in response.json()["detail"]
    assert _reload(db_session_factory, record_id).state == ImageLifecycleState.COLLECTED


def test_approve_404s_for_missing_record(client):
    assert client.post("/api/records/nope/approve").status_code == 404


# --------------------------------------------------------------------------- #
# 3. PATCH .../used pushes to PUBLISHED (AS_ACCEPTED sticky)
# --------------------------------------------------------------------------- #

def test_used_true_pushes_state_to_published(client, db_session_factory):
    record_id = _seed(
        db_session_factory, state=ImageLifecycleState.READY_TO_PUBLISH
    )

    response = client.patch(f"/api/records/{record_id}/used", json={"is_used": True})

    assert response.status_code == 200
    record = _reload(db_session_factory, record_id)
    assert record.is_used is True
    assert record.state == ImageLifecycleState.PUBLISHED


def test_used_true_does_not_leave_as_accepted(client, db_session_factory):
    record_id = _seed(db_session_factory, state=ImageLifecycleState.AS_ACCEPTED)

    response = client.patch(f"/api/records/{record_id}/used", json={"is_used": True})

    assert response.status_code == 200
    record = _reload(db_session_factory, record_id)
    assert record.is_used is True
    assert record.state == ImageLifecycleState.AS_ACCEPTED


def test_used_false_does_not_change_state(client, db_session_factory):
    record_id = _seed(db_session_factory, state=ImageLifecycleState.PUBLISHED)

    response = client.patch(f"/api/records/{record_id}/used", json={"is_used": False})

    assert response.status_code == 200
    record = _reload(db_session_factory, record_id)
    assert record.is_used is False
    assert record.state == ImageLifecycleState.PUBLISHED


def test_bulk_used_pushes_states_but_keeps_as_accepted(client, db_session_factory):
    queued = _seed(
        db_session_factory,
        filename="queued.jpg",
        state=ImageLifecycleState.READY_TO_PUBLISH,
    )
    accepted = _seed(
        db_session_factory,
        filename="accepted.jpg",
        state=ImageLifecycleState.AS_ACCEPTED,
    )

    response = client.patch(
        "/api/records/used",
        json={"record_ids": [queued, accepted], "is_used": True},
    )

    assert response.status_code == 200
    assert _reload(db_session_factory, queued).state == ImageLifecycleState.PUBLISHED
    assert _reload(db_session_factory, accepted).state == ImageLifecycleState.AS_ACCEPTED


# --------------------------------------------------------------------------- #
# 4. Flag derivation (compute_flags) — each flag, complement, display order
# --------------------------------------------------------------------------- #

def test_flags_always_carry_exactly_one_of_used_or_unused():
    fresh = _transient()
    assert compute_flags(fresh) == ["UNUSED"]

    used = _transient(is_used=True)
    assert compute_flags(used) == ["USED"]


def test_flag_quarantined_from_stage_and_sticky_from_blob():
    staged = _transient(stage=PipelineStage.QUARANTINED)
    assert "QUARANTINED" in compute_flags(staged)

    # Sticky: stage reset away, but the rejection decision is still stored.
    sticky = _transient(
        stage=PipelineStage.COLLECTED,
        stage_details={"diversity_gate": {"keep": False, "reason": "duplicate"}},
    )
    assert "QUARANTINED" in compute_flags(sticky)

    # A *kept* decision is evidence of scoring, not of quarantine.
    kept = _transient(
        stage=PipelineStage.COLLECTED,
        stage_details={"diversity_gate": {"keep": True, "reason": "sharpest"}},
    )
    assert "QUARANTINED" not in compute_flags(kept)


def test_flag_metadata_ready_from_blob_or_title():
    from_blob = _transient(stage_details={"metadata": {"keyword_count": 10}})
    assert "METADATA_READY" in compute_flags(from_blob)

    from_title = _transient(generated_title="A title")
    assert "METADATA_READY" in compute_flags(from_title)

    neither = _transient()
    assert "METADATA_READY" not in compute_flags(neither)


def test_flag_incompatible_from_stage_or_failed_blob():
    staged = _transient(stage=PipelineStage.INCOMPATIBLE)
    assert "INCOMPATIBLE" in compute_flags(staged)

    sticky = _transient(
        stage=PipelineStage.COLLECTED,
        stage_details={"compatibility": {"passed": False, "score": 0.31}},
    )
    assert "INCOMPATIBLE" in compute_flags(sticky)

    passed = _transient(
        stage=PipelineStage.COMPATIBLE,
        stage_details={"compatibility": {"passed": True, "score": 0.9}},
    )
    assert "INCOMPATIBLE" not in compute_flags(passed)


def test_flag_refined_from_pass_count():
    assert "REFINED" not in compute_flags(_transient(refine_passes=0))
    assert "REFINED" in compute_flags(_transient(refine_passes=2))


def test_flag_upscaled_from_blob():
    assert "UPSCALED" not in compute_flags(_transient())
    upscaled = _transient(stage_details={"upscale": {"backend": "resample"}})
    assert "UPSCALED" in compute_flags(upscaled)


def test_flag_ocr_rejected_from_stage_or_blocked_blob():
    staged = _transient(stage=PipelineStage.OCR_REJECTED)
    assert "OCR_REJECTED" in compute_flags(staged)

    sticky = _transient(
        stage=PipelineStage.COLLECTED,
        stage_details={"ocr": {"blocked": True, "reason": "brand text"}},
    )
    assert "OCR_REJECTED" in compute_flags(sticky)

    clear = _transient(
        stage=PipelineStage.OCR_CLEAR,
        stage_details={"ocr": {"blocked": False, "reason": None}},
    )
    assert "OCR_REJECTED" not in compute_flags(clear)


def test_flags_appear_in_the_exact_display_order():
    record = _transient(
        stage=PipelineStage.OCR_REJECTED,
        is_used=True,
        refine_passes=1,
        generated_title="Everything at once",
        stage_details={
            "diversity_gate": {"keep": False},
            "metadata": {"keyword_count": 5},
            "compatibility": {"passed": False},
            "upscale": {"backend": "resample"},
            "ocr": {"blocked": True},
        },
    )

    assert compute_flags(record) == [
        "QUARANTINED",
        "USED",
        "METADATA_READY",
        "INCOMPATIBLE",
        "REFINED",
        "UPSCALED",
        "OCR_REJECTED",
    ]


def test_record_response_carries_derived_state_and_flags(client, db_session_factory):
    record_id = _seed(
        db_session_factory,
        state=ImageLifecycleState.APPROVED,
        refine_passes=1,
        generated_title="Named",
    )

    item = client.get(f"/api/records/{record_id}").json()

    assert item["state"] == "APPROVED"
    assert item["flags"] == ["UNUSED", "METADATA_READY", "REFINED"]


# --------------------------------------------------------------------------- #
# refresh_state_for_stage — derived moves and sticky states
# --------------------------------------------------------------------------- #

def test_refresh_maps_stage_transitions_onto_the_state_axis():
    approved = _transient(
        stage=PipelineStage.METADATA_READY, state=ImageLifecycleState.COLLECTED
    )
    refresh_state_for_stage(approved)
    assert approved.state == ImageLifecycleState.APPROVED

    rejected = _transient(
        stage=PipelineStage.OCR_REJECTED, state=ImageLifecycleState.APPROVED
    )
    refresh_state_for_stage(rejected)
    assert rejected.state == ImageLifecycleState.REJECTED

    collected = _transient(
        stage=PipelineStage.COLLECTED, state=ImageLifecycleState.REJECTED
    )
    refresh_state_for_stage(collected)
    assert collected.state == ImageLifecycleState.COLLECTED


def test_refresh_keeps_queued_record_queued_but_drops_it_on_failure():
    queued = _transient(
        stage=PipelineStage.METADATA_READY,
        state=ImageLifecycleState.READY_TO_PUBLISH,
    )
    refresh_state_for_stage(queued)
    assert queued.state == ImageLifecycleState.READY_TO_PUBLISH

    queued_but_failed = _transient(
        stage=PipelineStage.QUARANTINED,
        state=ImageLifecycleState.READY_TO_PUBLISH,
    )
    refresh_state_for_stage(queued_but_failed)
    assert queued_but_failed.state == ImageLifecycleState.REJECTED


@pytest.mark.parametrize(
    "state",
    [ImageLifecycleState.PUBLISHED, ImageLifecycleState.AS_ACCEPTED],
)
def test_refresh_never_clobbers_published_or_accepted(state):
    record = _transient(stage=PipelineStage.INCOMPATIBLE, state=state)
    refresh_state_for_stage(record)
    assert record.state == state


# --------------------------------------------------------------------------- #
# Stage 7 publish gate — state, not stage, opens it
# --------------------------------------------------------------------------- #

def test_publish_refuses_a_record_that_was_not_queued(pipeline_env, monkeypatch):
    from tasks import audit_orchestrator, stage_orchestrator

    def _boom(*args, **kwargs):
        pytest.fail("publish must not run the approval pipeline for unqueued records")

    monkeypatch.setattr(audit_orchestrator, "process_approval", _boom)

    record_id = _seed(
        pipeline_env["factory"],
        state=ImageLifecycleState.APPROVED,
        stage=PipelineStage.METADATA_READY,
    )

    job_id = stage_orchestrator.publish_records(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )
    job = stage_orchestrator.registry.get(job_id)

    assert job.items[0].status == "failed"
    assert "READY_TO_PUBLISH" in job.items[0].message
    assert _reload(pipeline_env["factory"], record_id).state == (
        ImageLifecycleState.APPROVED
    )


def test_publish_success_marks_the_record_published(pipeline_env, monkeypatch):
    from tasks import audit_orchestrator, stage_orchestrator

    # Success without file work: the publish *state machine* is under test,
    # not the copy/embed pipeline (covered by test_delivery_api).
    monkeypatch.setattr(
        audit_orchestrator, "process_approval", lambda **kwargs: True
    )

    record_id = _seed(
        pipeline_env["factory"],
        state=ImageLifecycleState.READY_TO_PUBLISH,
        stage=PipelineStage.METADATA_READY,
        status=ImageStatus.PASSED,
    )

    job_id = stage_orchestrator.publish_records(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )
    job = stage_orchestrator.registry.get(job_id)

    assert job.items[0].status == "succeeded"
    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.PUBLISHED
    assert record.state == ImageLifecycleState.PUBLISHED
    assert record.status == ImageStatus.READY


# --------------------------------------------------------------------------- #
# 5. Migration backfill mapping
# --------------------------------------------------------------------------- #

#: (id, status, stage) rows in the pre-`state` schema, and the state they map to.
BACKFILL_CASES = [
    ("r1", "READY", "PUBLISHED", "PUBLISHED"),          # rule 1 wins
    ("r2", "READY", "METADATA_READY", "READY_TO_PUBLISH"),  # rule 2
    ("r3", "FLAGGED", "OCR_REJECTED", "REJECTED"),      # rule 3 (both markers)
    ("r4", "FLAGGED", "INCOMPATIBLE", "REJECTED"),
    ("r5", "PENDING", "QUARANTINED", "REJECTED"),       # rule 3 (stage only)
    ("r6", "PASSED", "METADATA_READY", "APPROVED"),     # rule 4
    ("r7", "PENDING", "COLLECTED", "COLLECTED"),        # rule 5 fallback
    ("r8", "PASSED", "PUBLISHED", "PUBLISHED"),         # rule 1 (stage only)
    ("r9", "APPROVED", "COMPATIBLE", "COLLECTED"),      # rule 5 fallback
]


def _legacy_engine():
    """A database shaped like the one before `state` existed."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE image_records (
                    id VARCHAR(36) PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    original_path VARCHAR(1024) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    stage VARCHAR(20) NOT NULL DEFAULT 'COLLECTED',
                    file_size_bytes INTEGER NOT NULL
                )
                """
            )
        )
        for record_id, status, stage, _expected in BACKFILL_CASES:
            connection.execute(
                text(
                    "INSERT INTO image_records "
                    "(id, filename, original_path, status, stage, file_size_bytes) "
                    "VALUES (:id, 'a.jpg', '/tmp/a.jpg', :status, :stage, 1)"
                ),
                {"id": record_id, "status": status, "stage": stage},
            )
    return engine


def test_state_backfill_maps_legacy_rows_by_precedence():
    from services.migrations import run_additive_migrations

    engine = _legacy_engine()
    try:
        applied = run_additive_migrations(engine)
        assert "image_records.state" in applied

        with engine.connect() as connection:
            rows = dict(
                connection.execute(text("SELECT id, state FROM image_records")).fetchall()
            )
        for record_id, _status, _stage, expected in BACKFILL_CASES:
            assert rows[record_id] == expected, f"{record_id} -> {rows[record_id]}"

        # The column is indexed even on a migrated database.
        with engine.connect() as connection:
            indexes = {
                row[1]
                for row in connection.execute(text("PRAGMA index_list(image_records)"))
            }
        assert "ix_image_records_state" in indexes
    finally:
        engine.dispose()


def test_state_backfill_runs_once_and_is_idempotent():
    from services.migrations import run_additive_migrations

    engine = _legacy_engine()
    try:
        run_additive_migrations(engine)

        # An operator's manual state must survive later startups untouched.
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE image_records SET state = 'AS_ACCEPTED' WHERE id = 'r6'")
            )
        second = run_additive_migrations(engine)
        assert second == []
        with engine.connect() as connection:
            state = connection.execute(
                text("SELECT state FROM image_records WHERE id = 'r6'")
            ).scalar_one()
        assert state == "AS_ACCEPTED"
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- #
# 6. ?state= filter and state_counts summary
# --------------------------------------------------------------------------- #

def test_records_filters_by_comma_separated_states(client, db_session_factory):
    approved = _seed(
        db_session_factory,
        filename="approved.jpg",
        state=ImageLifecycleState.APPROVED,
    )
    _seed(
        db_session_factory,
        filename="rejected.jpg",
        state=ImageLifecycleState.REJECTED,
    )
    _seed(
        db_session_factory,
        filename="queued.jpg",
        state=ImageLifecycleState.READY_TO_PUBLISH,
    )

    both = client.get(
        "/api/records", params={"state": "APPROVED,REJECTED"}
    ).json()
    assert both["total"] == 2
    ids = {item["id"] for item in both["items"]}
    assert approved in ids
    assert len(ids) == 2

    single = client.get("/api/records", params={"state": "READY_TO_PUBLISH"}).json()
    assert single["total"] == 1
    assert single["items"][0]["state"] == "READY_TO_PUBLISH"


def test_records_state_filter_combines_with_existing_filters(
    client, db_session_factory
):
    kept = _seed(
        db_session_factory,
        filename="kept.jpg",
        state=ImageLifecycleState.PUBLISHED,
        is_used=True,
    )
    _seed(
        db_session_factory,
        filename="queued.jpg",
        state=ImageLifecycleState.PUBLISHED,
        is_used=False,
    )

    body = client.get(
        "/api/records", params={"state": "PUBLISHED", "used": "used"}
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == kept


def test_records_rejects_invalid_state_filter(client):
    response = client.get("/api/records", params={"state": "BOGUS"})

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "Invalid state(s): BOGUS" in detail
    for value in ALL_STATES:
        assert value in detail


def test_stage_summary_zero_fills_every_state(client, db_session_factory):
    _seed(db_session_factory, filename="a.jpg", state=ImageLifecycleState.APPROVED)
    _seed(db_session_factory, filename="b.jpg", state=ImageLifecycleState.APPROVED)
    _seed(db_session_factory, filename="c.jpg", state=ImageLifecycleState.PUBLISHED)

    body = client.get("/api/stages/summary").json()

    assert set(body["state_counts"]) == ALL_STATES
    assert body["state_counts"]["APPROVED"] == 2
    assert body["state_counts"]["PUBLISHED"] == 1
    assert body["state_counts"]["COLLECTED"] == 0
    assert body["state_counts"]["AS_ACCEPTED"] == 0
    # The legacy shape stays intact.
    assert len(body["counts"]) == len(PipelineStage)
    assert body["total"] == 3
