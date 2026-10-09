"""Gallery folders and current-file serving (groups + gallery_files routers).

Uses the suite's shared ``client`` fixture (in-memory DB, overridden
``get_db``) — never the real storage database.
"""

from __future__ import annotations

import uuid

import pytest

from models import ImageRecord, ImageStatus, PipelineStage


@pytest.fixture()
def db_session(db_session_factory):
    """A live session on the same in-memory DB the client fixture serves."""
    session = db_session_factory()
    try:
        yield session
    finally:
        session.close()


def _make_record(db, filename="photo.jpg") -> str:
    record_id = str(uuid.uuid4())
    db.add(
        ImageRecord(
            id=record_id,
            filename=filename,
            original_path=f"C:/nowhere/{filename}",
            status=ImageStatus.PENDING,
            stage=PipelineStage.COLLECTED,
            file_size_bytes=1024,
        )
    )
    db.commit()
    return record_id


class TestGroups:
    def test_create_list_rename_delete(self, client):
        created = client.post("/api/groups", json={"name": "  Client A  "})
        assert created.status_code == 201
        group = created.json()
        assert group["name"] == "Client A"  # whitespace collapsed
        assert group["image_count"] == 0

        listed = client.get("/api/groups")
        assert listed.status_code == 200
        assert [g["id"] for g in listed.json()["items"]] == [group["id"]]

        renamed = client.patch(f"/api/groups/{group['id']}", json={"name": "Client B"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Client B"

        deleted = client.delete(f"/api/groups/{group['id']}")
        assert deleted.status_code == 200
        assert client.get("/api/groups").json()["items"] == []

    def test_empty_name_rejected(self, client):
        assert client.post("/api/groups", json={"name": "   "}).status_code == 400

    def test_create_with_records_and_assign_out(self, client, db_session):
        rid = _make_record(db_session)
        group = client.post(
            "/api/groups", json={"name": "Set 1", "record_ids": [rid]}
        ).json()
        assert group["image_count"] == 1

        # Records list scoped to the group sees it; 'none' does not.
        in_group = client.get(f"/api/records?group_id={group['id']}").json()
        assert [r["id"] for r in in_group["items"]] == [rid]
        ungrouped = client.get("/api/records?group_id=none").json()
        assert ungrouped["items"] == []

        # Assign out (ungroup).
        moved = client.put("/api/groups/assign", json={"record_ids": [rid], "group_id": None})
        assert moved.status_code == 200
        assert moved.json()["updated"] == 1
        assert client.get("/api/records?group_id=none").json()["total"] == 1

    def test_delete_group_keeps_images(self, client, db_session):
        rid = _make_record(db_session)
        group = client.post(
            "/api/groups", json={"name": "Temp", "record_ids": [rid]}
        ).json()
        client.delete(f"/api/groups/{group['id']}")
        # The image survives and is back at the top level.
        record = db_session.get(ImageRecord, rid)
        assert record is not None and record.group_id is None

    def test_assign_to_missing_group_404(self, client, db_session):
        rid = _make_record(db_session)
        resp = client.put(
            "/api/groups/assign",
            json={"record_ids": [rid], "group_id": "nope"},
        )
        assert resp.status_code == 404


class TestGalleryFiles:
    def test_missing_file_404(self, client, db_session):
        rid = _make_record(db_session)
        resp = client.get(f"/api/records/{rid}/file")
        assert resp.status_code == 404

    def test_serves_inline_and_download(self, client, db_session, tmp_path):
        image = tmp_path / "cut.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\n fake")
        rid = _make_record(db_session, filename="cut.png")
        record = db_session.get(ImageRecord, rid)
        record.original_path = str(image)
        db_session.commit()

        inline = client.get(f"/api/records/{rid}/file")
        assert inline.status_code == 200
        assert inline.headers["content-type"].startswith("image/png")
        assert "attachment" not in inline.headers.get("content-disposition", "")

        dl = client.get(f"/api/records/{rid}/file?download=1")
        assert dl.status_code == 200
        assert "attachment" in dl.headers["content-disposition"]

    def test_zip_roundtrip(self, client, db_session, tmp_path):
        image = tmp_path / "a.jpg"
        image.write_bytes(b"jpegbytes")
        rid = _make_record(db_session, filename="a.jpg")
        record = db_session.get(ImageRecord, rid)
        record.original_path = str(image)
        db_session.commit()

        resp = client.post("/api/records/file-zip", json={"record_ids": [rid]})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_zip_rejects_empty_and_oversized(self, client):
        assert client.post("/api/records/file-zip", json={"record_ids": []}).status_code == 400
        too_many = [str(i) for i in range(201)]
        assert (
            client.post("/api/records/file-zip", json={"record_ids": too_many}).status_code
            == 400
        )
