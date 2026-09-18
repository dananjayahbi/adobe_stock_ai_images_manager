"""Integration tests for the records listing endpoint."""


def test_records_empty_initially(client):
    response = client.get("/api/records")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_records_rejects_invalid_status(client):
    response = client.get("/api/records", params={"status": "NOT_A_STATUS"})

    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]


def test_records_rejects_negative_limit(client):
    response = client.get("/api/records", params={"limit": -1})

    assert response.status_code == 400


def test_records_rejects_limit_above_maximum(client):
    response = client.get("/api/records", params={"limit": 501})

    assert response.status_code == 400


def test_records_accepts_valid_status_filter(client):
    response = client.get("/api/records", params={"status": "PASSED"})

    assert response.status_code == 200
    assert response.json()["items"] == []


def test_records_serializes_list_shaped_semantic_flags(client, db_session_factory):
    """Regression: semantic_flags is a list of strings, not a dict."""
    from models import ImageRecord, ImageStatus

    session = db_session_factory()
    session.add(
        ImageRecord(
            filename="flagged.jpg",
            original_path="/tmp/flagged.jpg",
            status=ImageStatus.FLAGGED,
            file_size_bytes=1024,
            semantic_flags=["sharpness: Laplacian variance 0.00 below minimum 120.0"],
        )
    )
    session.commit()
    session.close()

    response = client.get("/api/records")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["semantic_flags"] == [
        "sharpness: Laplacian variance 0.00 below minimum 120.0"
    ]
