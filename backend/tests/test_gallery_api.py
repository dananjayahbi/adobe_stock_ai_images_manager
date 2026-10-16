"""Integration tests for the gallery endpoints (usage, delete, download, table)."""

from pathlib import Path

from models import ImageLifecycleState, ImageRecord, ImageStatus


def _seed_record(db_session_factory, tmp_path, **overrides):
    """Insert a record with sensible defaults and return its id."""
    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(parents=True, exist_ok=True)

    record_id = overrides.pop("id", None)
    original = tmp_path / overrides.pop("original_name", "asset.jpg")
    original.write_bytes(b"fake-jpeg-bytes")

    ready = ready_dir / f"{record_id or 'pending'}.jpg"

    defaults = dict(
        filename="asset.jpg",
        original_path=str(original),
        thumbnail_path=None,
        status=ImageStatus.READY,
        # The seeded record models an upload-ready asset, so it must be
        # queued for publish — that is now what the download gate reads.
        state=ImageLifecycleState.READY_TO_PUBLISH,
        file_size_bytes=original.stat().st_size,
        generated_title="Sunset Over Calm Ocean",
        generated_description="A calm ocean at sunset.",
        generated_keywords=["sunset", "ocean", "calm"],
    )
    defaults.update(overrides)

    session = db_session_factory()
    record = ImageRecord(**defaults)
    session.add(record)
    session.commit()
    session.refresh(record)
    record_id = record.id
    session.close()

    # Materialize the staged file using the real record id.
    staged = ready_dir / f"{record_id}.jpg"
    staged.write_bytes(b"staged-bytes")
    return record_id


def test_mark_record_used_and_filter(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    response = client.patch(
        f"/api/records/{record_id}/used", json={"is_used": True}
    )
    assert response.status_code == 200
    assert response.json()["updated"] == 1

    unused = client.get("/api/records", params={"used": "unused"}).json()
    assert unused["total"] == 0

    used = client.get("/api/records", params={"used": "used"}).json()
    assert used["total"] == 1
    assert used["items"][0]["is_used"] is True
    assert used["items"][0]["used_at"] is not None

    every = client.get("/api/records", params={"used": "all"}).json()
    assert every["total"] == 1


def test_mark_record_unused_clears_timestamp(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    client.patch(f"/api/records/{record_id}/used", json={"is_used": True})
    client.patch(f"/api/records/{record_id}/used", json={"is_used": False})

    item = client.get("/api/records").json()["items"][0]
    assert item["is_used"] is False
    assert item["used_at"] is None


def test_bulk_used_reports_missing_ids(client, db_session_factory, tmp_path):
    first = _seed_record(db_session_factory, tmp_path, original_name="a.jpg")
    second = _seed_record(db_session_factory, tmp_path, original_name="b.jpg")

    response = client.patch(
        "/api/records/used",
        json={"record_ids": [first, second, "does-not-exist"], "is_used": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    assert body["missing"] == ["does-not-exist"]


def test_records_rejects_invalid_used_filter(client):
    response = client.get("/api/records", params={"used": "maybe"})

    assert response.status_code == 400
    assert "Invalid usage filter" in response.json()["detail"]


def test_records_ids_filter(client, db_session_factory, tmp_path):
    first = _seed_record(db_session_factory, tmp_path, original_name="a.jpg")
    _seed_record(db_session_factory, tmp_path, original_name="b.jpg")

    response = client.get("/api/records", params={"ids": first})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == first


def test_get_single_record(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    response = client.get(f"/api/records/{record_id}")

    assert response.status_code == 200
    assert response.json()["id"] == record_id


def test_get_single_record_missing(client):
    response = client.get("/api/records/nope")

    assert response.status_code == 404


def test_delete_record_removes_files(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)
    staged = tmp_path / "ready" / f"{record_id}.jpg"
    assert staged.is_file()

    response = client.delete(f"/api/records/{record_id}")

    assert response.status_code == 200
    assert response.json()["deleted"] == 1
    assert not staged.exists()
    assert client.get("/api/records").json()["total"] == 0


def test_bulk_delete_reports_missing(client, db_session_factory, tmp_path):
    first = _seed_record(db_session_factory, tmp_path, original_name="a.jpg")
    second = _seed_record(db_session_factory, tmp_path, original_name="b.jpg")

    response = client.post(
        "/api/records/bulk-delete",
        json={"record_ids": [first, second, "ghost"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == 2
    assert body["missing"] == ["ghost"]
    assert client.get("/api/records").json()["total"] == 0


def test_bulk_delete_rejects_empty(client):
    response = client.post("/api/records/bulk-delete", json={"record_ids": []})

    assert response.status_code == 400


def test_download_ready_record(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    response = client.get(f"/api/records/{record_id}/download")

    assert response.status_code == 200
    assert response.content == b"staged-bytes"
    assert "sunset-over-calm-ocean.jpg" in response.headers["content-disposition"]


def test_download_rejects_non_ready_record(client, db_session_factory, tmp_path):
    record_id = _seed_record(
        db_session_factory,
        tmp_path,
        status=ImageStatus.PASSED,
        state=ImageLifecycleState.COLLECTED,
    )

    response = client.get(f"/api/records/{record_id}/download")

    assert response.status_code == 409
    detail = response.json()["detail"]
    # The gate reads lifecycle states now, and says which ones open it.
    assert "COLLECTED" in detail
    assert "READY_TO_PUBLISH" in detail


def test_download_missing_staged_file(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)
    (tmp_path / "ready" / f"{record_id}.jpg").unlink()

    response = client.get(f"/api/records/{record_id}/download")

    assert response.status_code == 404


def test_download_zip_bundles_staged_files(client, db_session_factory, tmp_path):
    import io
    import zipfile

    first = _seed_record(db_session_factory, tmp_path, original_name="a.jpg")
    second = _seed_record(db_session_factory, tmp_path, original_name="b.jpg")

    response = client.post(
        "/api/records/download-zip", json={"record_ids": [first, second]}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == 2


def test_download_zip_rejects_empty(client):
    response = client.post("/api/records/download-zip", json={"record_ids": []})

    assert response.status_code == 400


def test_upload_table_returns_metadata_rows(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    response = client.post("/api/upload-table", json={"record_ids": [record_id]})

    assert response.status_code == 200
    body = response.json()
    assert body["missing"] == []
    item = body["items"][0]
    assert item["record_id"] == record_id
    assert item["title"] == "Sunset Over Calm Ocean"
    assert item["keywords"] == ["sunset", "ocean", "calm"]
    assert item["keywords_csv"] == "sunset, ocean, calm"
    assert item["download_url"].endswith(f"/api/records/{record_id}/download")


def test_upload_table_preserves_requested_order(client, db_session_factory, tmp_path):
    first = _seed_record(db_session_factory, tmp_path, original_name="a.jpg")
    second = _seed_record(db_session_factory, tmp_path, original_name="b.jpg")

    response = client.post(
        "/api/upload-table", json={"record_ids": [second, first]}
    )

    assert response.status_code == 200
    ids = [item["record_id"] for item in response.json()["items"]]
    assert ids == [second, first]


def test_upload_table_reports_missing(client, db_session_factory, tmp_path):
    record_id = _seed_record(db_session_factory, tmp_path)

    response = client.post(
        "/api/upload-table", json={"record_ids": [record_id, "ghost"]}
    )

    assert response.status_code == 200
    assert response.json()["missing"] == ["ghost"]


def test_upload_table_rejects_empty(client):
    response = client.post("/api/upload-table", json={"record_ids": []})

    assert response.status_code == 400
