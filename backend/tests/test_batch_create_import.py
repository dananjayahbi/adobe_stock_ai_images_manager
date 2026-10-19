"""Tests for server-side batch creation with ``files`` (source-folder import).

The import path must behave like the upload endpoint — same inbox copy,
conversion, thumbnail, and record insert — while validating *before* the batch
exists: configured folder (400), containment (403), existence + extension
(400), image cap (409).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from models import ImageRecord
from tests.test_batch_pipeline import _jpg_bytes, _png_bytes


@pytest.fixture()
def source_root(client, tmp_path):
    """A configured source folder with importable files, a decoy, a subdir."""
    root = tmp_path / "source"
    root.mkdir()
    (root / "photo.jpg").write_bytes(_jpg_bytes())
    (root / "object.png").write_bytes(_png_bytes())
    (root / "notes.txt").write_bytes(b"not an image")
    (root / "sub").mkdir()
    (root / "sub" / "nested.jpg").write_bytes(_jpg_bytes())
    # Outside the root, for the containment (403) case.
    (tmp_path / "outside.jpg").write_bytes(_jpg_bytes())

    response = client.put("/api/settings", json={"source_folder": str(root)})
    assert response.status_code == 200, response.text
    return root


def _create_with_files(client, files, **extra):
    payload = {
        "name": "Imported",
        "media_type": "raster",
        "steps": [{"key": "ocr"}],
        "files": files,
        **extra,
    }
    return client.post("/api/batches", json=payload)


def _batch_total(client) -> int:
    return client.get("/api/batches").json()["total"]


class TestCreateWithFilesHappyPath:
    def test_import_copies_converts_and_creates_records(
        self, client, db_session_factory, source_root
    ):
        from config import settings

        response = _create_with_files(client, ["photo.jpg", "object.png"])
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "draft"
        assert body["record_count"] == 2
        assert body["queued_at"] is None

        session = db_session_factory()
        records = (
            session.query(ImageRecord).filter_by(batch_id=body["id"]).all()
        )
        assert len(records) == 2
        for record in records:
            # The inbox copy is the working artifact; the source is untouched.
            original = Path(record.original_path)
            assert original.is_file()
            assert original.parent == Path(settings.INBOX_DIR)
        # Raster batch: the PNG was normalised to JPEG like an upload is.
        png_record = next(r for r in records if r.filename == "object.png")
        assert Path(png_record.working_path).suffix == ".jpg"
        assert png_record.thumbnail_path
        session.close()

        assert (source_root / "photo.jpg").is_file()
        assert (source_root / "object.png").is_file()

    def test_png_batch_keeps_alpha_on_import(
        self, client, db_session_factory, source_root
    ):
        response = _create_with_files(
            client, ["object.png"], media_type="png",
            steps=[{"key": "bg_remove"}],
        )
        assert response.status_code == 201, response.text

        session = db_session_factory()
        record = (
            session.query(ImageRecord).filter_by(batch_id=response.json()["id"]).one()
        )
        assert record.working_path == record.original_path
        assert record.working_path.endswith(".png")
        session.close()

    def test_import_from_a_subdirectory(self, client, db_session_factory, source_root):
        response = _create_with_files(client, ["sub/nested.jpg"])
        assert response.status_code == 201, response.text

        session = db_session_factory()
        record = (
            session.query(ImageRecord).filter_by(batch_id=response.json()["id"]).one()
        )
        assert record.filename == "nested.jpg"
        session.close()

    def test_files_null_keeps_the_legacy_empty_draft(
        self, client, source_root
    ):
        payload = {
            "name": "Legacy",
            "media_type": "raster",
            "steps": [{"key": "ocr"}],
        }
        response = client.post("/api/batches", json=payload)
        assert response.status_code == 201
        assert response.json()["record_count"] == 0

    def test_empty_files_list_creates_an_empty_draft(self, client, source_root):
        response = _create_with_files(client, [])
        assert response.status_code == 201
        assert response.json()["record_count"] == 0


class TestCreateWithFilesGuards:
    def test_unconfigured_source_folder_is_400(self, client):
        # No PUT: the settings store (isolated per test) has no source_folder.
        response = _create_with_files(client, ["photo.jpg"])
        assert response.status_code == 400
        assert "source folder" in response.json()["detail"].lower()
        assert _batch_total(client) == 0

    def test_escape_outside_the_root_is_403(self, client, source_root):
        response = _create_with_files(client, ["../outside.jpg"])
        assert response.status_code == 403
        assert "escape" in response.json()["detail"].lower()
        assert _batch_total(client) == 0

    def test_backslash_escape_is_403(self, client, source_root):
        response = _create_with_files(client, ["..\\outside.jpg"])
        assert response.status_code == 403
        assert _batch_total(client) == 0

    def test_missing_file_is_400_naming_the_path(self, client, source_root):
        response = _create_with_files(client, ["ghost.jpg"])
        assert response.status_code == 400
        assert "ghost.jpg" in response.json()["detail"]
        assert _batch_total(client) == 0

    def test_bad_extension_is_400_naming_the_path(self, client, source_root):
        response = _create_with_files(client, ["notes.txt"])
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "notes.txt" in detail
        assert ".jpg" in detail  # the allowed set is spelled out, like upload
        assert _batch_total(client) == 0

    def test_batch_image_cap_is_409(
        self, client, source_root, monkeypatch
    ):
        from routers import batches as batches_router

        monkeypatch.setattr(batches_router, "MAX_BATCH_IMAGES", 2)
        response = _create_with_files(
            client, ["photo.jpg", "object.png", "sub/nested.jpg"]
        )
        assert response.status_code == 409
        assert "at most 2" in response.json()["detail"]
        assert _batch_total(client) == 0

    def test_validation_runs_before_the_batch_row_exists(
        self, client, source_root
    ):
        """A batch with one good path and one bad path creates nothing."""
        response = _create_with_files(client, ["photo.jpg", "../outside.jpg"])
        assert response.status_code == 403
        assert _batch_total(client) == 0
