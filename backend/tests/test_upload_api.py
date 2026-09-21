"""Integration tests for the upload endpoint."""


def _jpeg_bytes() -> bytes:
    """Minimal valid JPEG payload for upload tests."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 120, 60)).save(buffer, "JPEG")
    return buffer.getvalue()


def _png_bytes(size=(64, 64), mode="RGB", color=(200, 120, 60)) -> bytes:
    """Minimal valid PNG payload for the Collector's conversion path."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, color).save(buffer, "PNG")
    return buffer.getvalue()


def test_upload_accepts_valid_jpeg(client):
    response = client.post(
        "/upload",
        files={"files": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert len(body["record_ids"]) == 1


def test_upload_creates_pending_record(client):
    client.post(
        "/upload",
        files={"files": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
    )

    listing = client.get("/api/records").json()
    assert listing["total"] == 1
    assert listing["items"][0]["status"] == "PENDING"
    assert listing["items"][0]["filename"] == "photo.jpg"


def test_upload_rejects_non_jpeg(client):
    response = client.post(
        "/upload",
        files={"files": ("notes.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 400
    assert "extension" in response.json()["detail"].lower()


def test_upload_rejects_empty_request(client):
    response = client.post("/upload")

    assert response.status_code in (400, 422)


# --------------------------------------------------------------------------- #
# PNG -> JPEG normalisation at the Collector
# --------------------------------------------------------------------------- #

def test_upload_accepts_png(client):
    """PNG is common AI output, so the Collector accepts it and converts it."""
    response = client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_uploaded_png_becomes_a_jpeg_working_copy(client):
    from pathlib import Path

    from config import settings

    client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(size=(120, 90)), "image/png")},
    )

    record = client.get("/api/records").json()["items"][0]

    # The working copy is a JPEG; the original stays a PNG in the inbox.
    assert Path(record["working_path"]).suffix.lower() == ".jpg"
    assert Path(record["original_path"]).suffix.lower() == ".png"
    assert Path(record["working_path"]).is_file()
    assert Path(record["original_path"]).is_file()

    # It lives in the converted directory, named after the record id.
    assert Path(record["working_path"]).parent == Path(settings.CONVERTED_DIR)
    assert Path(record["working_path"]).stem == record["id"]


def test_png_conversion_is_recorded_in_the_stage_details(client):
    client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(), "image/png")},
    )

    details = client.get("/api/records").json()["items"][0]["stage_details"]

    assert details is not None
    assert details["collector"]["converted"] is True
    assert details["collector"]["source_suffix"] == ".png"


def test_jpeg_upload_is_not_marked_as_converted(client):
    """A JPEG must not be re-encoded: that would be a free generation of loss."""
    from pathlib import Path

    from config import settings

    client.post(
        "/upload",
        files={"files": ("photo.jpg", _jpeg_bytes(), "image/jpeg")},
    )

    record = client.get("/api/records").json()["items"][0]

    assert record["stage_details"] is None
    # The working copy is the inbox original, not a converted duplicate.
    assert Path(record["working_path"]) == Path(record["original_path"])
    assert not any(Path(settings.CONVERTED_DIR).glob("*.jpg"))


def test_png_thumbnail_is_generated_from_the_converted_jpeg(client):
    from pathlib import Path

    client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(), "image/png")},
    )

    record = client.get("/api/records").json()["items"][0]
    assert record["thumbnail_path"]
    assert Path(record["thumbnail_path"]).is_file()


def test_png_dimensions_are_recorded(client):
    client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(size=(160, 120)), "image/png")},
    )

    record = client.get("/api/records").json()["items"][0]
    assert (record["width"], record["height"]) == (160, 120)
    assert record["megapixels"] == 0.02


def test_mixed_batch_converts_only_the_pngs(client):
    from pathlib import Path

    from config import settings

    client.post(
        "/upload",
        files=[
            ("files", ("a.jpg", _jpeg_bytes(), "image/jpeg")),
            ("files", ("b.png", _png_bytes(), "image/png")),
        ],
    )

    records = client.get("/api/records").json()["items"]
    assert len(records) == 2

    converted = list(Path(settings.CONVERTED_DIR).glob("*.jpg"))
    assert len(converted) == 1

    by_name = {record["filename"]: record for record in records}
    assert Path(by_name["a.jpg"]["working_path"]).suffix.lower() == ".jpg"
    assert Path(by_name["b.png"]["working_path"]).suffix.lower() == ".jpg"


def test_deleting_a_png_record_removes_the_converted_copy(client):
    from pathlib import Path

    from config import settings

    client.post(
        "/upload",
        files={"files": ("render.png", _png_bytes(), "image/png")},
    )
    record = client.get("/api/records").json()["items"][0]
    converted = Path(record["working_path"])
    assert converted.is_file()

    response = client.delete(f"/api/records/{record['id']}")
    assert response.status_code == 200

    assert not converted.exists()
    assert list(Path(settings.CONVERTED_DIR).glob("*.jpg")) == []

