"""API tests for the duplicate-similarity scan endpoint.

The scan is advisory, so these tests focus on two things: that it finds the
patterns Adobe actually refuses content for, and that it never fails a request
just because an image is unreadable.
"""

from models import ImageRecord, PipelineStage


def _seed(db_session_factory, tmp_path, **overrides) -> str:
    """Insert a record with sensible defaults and return its id.

    The image file is deliberately absent in most cases, so the scan falls back
    to the metadata signal alone - which is the pattern Adobe names as its own
    refusal reason ("different images tagged with identical titles and
    keywords").
    """
    record_id = overrides.pop("id", None)
    original = tmp_path / overrides.pop("original_name", "asset.jpg")
    original.write_bytes(b"fake-jpeg-bytes")

    defaults = dict(
        filename="asset.jpg",
        original_path=str(original),
        thumbnail_path=None,
        status="PENDING",
        stage=PipelineStage.METADATA_READY,
        file_size_bytes=original.stat().st_size,
        generated_title="A generated title",
        generated_description="A description.",
        generated_keywords=["one", "two"],
        category=8,
    )
    defaults.update(overrides)
    if record_id:
        defaults["id"] = record_id

    session = db_session_factory()
    record = ImageRecord(**defaults)
    session.add(record)
    session.commit()
    session.refresh(record)
    record_id = record.id
    session.close()
    return record_id


def _scan(client, **payload):
    return client.post("/api/similarity/scan", json=payload)


# --------------------------------------------------------------------------- #
# Finding the patterns Adobe refuses
# --------------------------------------------------------------------------- #

def test_scan_reports_reused_metadata_as_similar(client, db_session_factory, tmp_path):
    """Adobe names this exact pattern: different images, identical metadata."""
    title = "Modern office workspace with laptop and coffee"
    keywords = ["office", "workspace", "laptop", "coffee", "business"]
    left = _seed(
        db_session_factory,
        tmp_path,
        id="a",
        generated_title=title,
        generated_keywords=keywords,
    )
    right = _seed(
        db_session_factory,
        tmp_path,
        id="b",
        generated_title=title,
        generated_keywords=keywords,
    )

    response = _scan(client, record_ids=[left, right])
    assert response.status_code == 200

    payload = response.json()
    assert payload["pair_count"] >= 1
    assert len(payload["groups"]) == 1
    assert set(payload["groups"][0]["record_ids"]) == {"a", "b"}
    assert payload["groups"][0]["reason"] in ("metadata", "both")


def test_scan_leaves_unrelated_records_alone(client, db_session_factory, tmp_path):
    left = _seed(
        db_session_factory,
        tmp_path,
        id="a",
        generated_title="Sunrise over a quiet mountain lake",
        generated_keywords=["sunrise", "mountain", "lake"],
    )
    right = _seed(
        db_session_factory,
        tmp_path,
        id="b",
        generated_title="Busy city intersection with yellow taxis",
        generated_keywords=["city", "traffic", "taxi"],
    )

    response = _scan(client, record_ids=[left, right])
    assert response.status_code == 200
    assert response.json()["groups"] == []


def test_scan_suggests_a_keep_set_per_group(client, db_session_factory, tmp_path):
    """Adobe: submit three to five per subject, angle, or pose."""
    title = "Shared subject photographed repeatedly"
    keywords = ["shared", "subject", "studio"]
    ids = [
        _seed(
            db_session_factory,
            tmp_path,
            id=f"rec-{index}",
            generated_title=title,
            generated_keywords=keywords,
        )
        for index in range(8)
    ]

    response = _scan(client, record_ids=ids, keep_per_group=5)
    payload = response.json()

    assert len(payload["groups"]) == 1
    group = payload["groups"][0]
    assert len(group["suggested_keep"]) == 5
    assert len(group["suggested_drop"]) == 3
    assert payload["suggested_drop_count"] == 3
    # The recommendation is explained rather than asserted silently.
    assert any("three to five" in note for note in payload["notes"])


# --------------------------------------------------------------------------- #
# Robustness
# --------------------------------------------------------------------------- #

def test_scan_handles_records_without_metadata(client, db_session_factory, tmp_path):
    """A record with no readable image and no metadata cannot be compared."""
    record_id = _seed(
        db_session_factory,
        tmp_path,
        id="empty",
        original_name="missing.jpg",
        generated_title=None,
        generated_keywords=None,
    )
    (tmp_path / "missing.jpg").unlink()

    response = _scan(client, record_ids=[record_id])
    assert response.status_code == 200

    payload = response.json()
    assert payload["scanned"] == 0
    assert payload["skipped"] == ["empty"]
    assert payload["groups"] == []


def test_scan_rejects_an_oversized_selection(client):
    too_many = [f"rec-{index}" for index in range(500)]

    response = _scan(client, record_ids=too_many)
    assert response.status_code == 400
    assert "400" in response.json()["detail"]


def test_scan_defaults_to_records_that_have_metadata(client, db_session_factory, tmp_path):
    title = "Shared title across two records"
    keywords = ["shared", "title", "pair"]
    _seed(db_session_factory, tmp_path, id="a", generated_title=title, generated_keywords=keywords)
    _seed(db_session_factory, tmp_path, id="b", generated_title=title, generated_keywords=keywords)
    # A COLLECTED record has no metadata yet, so the default scan ignores it.
    _seed(
        db_session_factory,
        tmp_path,
        id="c",
        stage=PipelineStage.COLLECTED,
        generated_title=None,
        generated_keywords=None,
    )

    response = _scan(client)
    assert response.status_code == 200

    payload = response.json()
    involved = {rid for group in payload["groups"] for rid in group["record_ids"]}
    assert "c" not in involved


def test_scan_respects_a_custom_threshold(client, db_session_factory, tmp_path):
    """A very high threshold should stop partially-overlapping metadata pairing."""
    _seed(
        db_session_factory,
        tmp_path,
        id="a",
        generated_title="alpha beta gamma",
        generated_keywords=["x"],
    )
    _seed(
        db_session_factory,
        tmp_path,
        id="b",
        generated_title="alpha beta delta",
        generated_keywords=["y"],
    )

    strict = _scan(client, record_ids=["a", "b"], metadata_threshold=0.99)
    assert strict.status_code == 200
    assert strict.json()["pair_count"] == 0


def test_scan_reports_no_notes_when_nothing_is_similar(client, db_session_factory, tmp_path):
    _seed(db_session_factory, tmp_path, id="solo")

    response = _scan(client, record_ids=["solo"])
    assert response.status_code == 200

    payload = response.json()
    assert payload["groups"] == []
    assert payload["notes"] == []
    assert payload["suggested_drop_count"] == 0
