"""Integration tests for the upload endpoint."""


def _jpeg_bytes() -> bytes:
    """Minimal valid JPEG payload for upload tests."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), color=(200, 120, 60)).save(buffer, "JPEG")
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
