from pathlib import Path

import pytest
from PIL import Image

from app.core.storage import StorageLayout
from app.ingestion import IngestionService, ValidationFailure


def make_jpeg(path: Path, size=(100, 80)) -> None:
    Image.new("RGB", size, (20, 40, 60)).save(path, format="JPEG")


def test_upload_normalizes_name_and_registers_source(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024 * 1024)
    source = tmp_path / "upload.jpg"
    make_jpeg(source)

    result = service.ingest(source, "../unsafe\\catalog photo.jpg", "batch-1")

    assert result.accepted is True
    assert result.asset_id
    assert result.display_name == "catalog photo.jpg"
    assert result.source_path.exists()
    assert layout.contains(result.source_path)
    assert result.source_path.read_bytes() == source.read_bytes()


def test_upload_rejects_non_image_and_does_not_create_asset(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024)
    source = tmp_path / "not-image.jpg"
    source.write_bytes(b"not a jpeg")

    with pytest.raises(ValidationFailure, match="decode"):
        service.ingest(source, "not-image.jpg", "batch-1")

    assert not list(layout.inbox.glob("*"))


def test_upload_is_deduplicated_by_source_hash(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024 * 1024)
    first = tmp_path / "first.jpg"
    second = tmp_path / "second.jpg"
    make_jpeg(first)
    second.write_bytes(first.read_bytes())

    one = service.ingest(first, "first.jpg", "batch-1")
    two = service.ingest(second, "second.jpg", "batch-2")

    assert two.duplicate is True
    assert two.asset_id == one.asset_id
    assert len(list(layout.inbox.glob("*"))) == 1


def test_thumbnail_generation_is_idempotent_and_bounded(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024 * 1024)
    source = tmp_path / "large.jpg"
    make_jpeg(source, (1200, 800))
    result = service.ingest(source, "large.jpg", "batch-1")

    first = service.create_thumbnail(result)
    second = service.create_thumbnail(result)

    assert first == second
    with Image.open(first) as thumbnail:
        assert thumbnail.width <= 400
        assert thumbnail.height <= 400


def test_normalization_preserves_source_and_is_idempotent(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024 * 1024)
    source = tmp_path / "source.png"
    Image.new("RGBA", (120, 80), (20, 40, 60, 128)).save(source, format="PNG")
    original_bytes = source.read_bytes()
    result = service.ingest(source, "source.png", "batch-1")

    first = service.normalize(result)
    second = service.normalize(result)

    assert first == second
    assert source.read_bytes() == original_bytes
    with Image.open(first) as normalized:
        assert normalized.format == "JPEG"
        assert normalized.mode == "RGB"


def test_jobs_are_claimed_once_and_finished_with_explicit_state(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    service = IngestionService(layout, max_file_size=1024 * 1024)
    source = tmp_path / "source.jpg"
    make_jpeg(source)
    result = service.ingest(source, "source.jpg", "batch-1")
    job_id = service.database.enqueue_job(result.asset_id, "thumbnail", result.source_hash)

    claimed = service.database.claim_next_job("thumbnail", "worker-1")
    second_claim = service.database.claim_next_job("thumbnail", "worker-2")
    service.database.finish_job(job_id, succeeded=True)
    state = service.database.connection.execute("SELECT state FROM jobs WHERE id = ?", (job_id,)).fetchone()[0]

    assert claimed["id"] == job_id
    assert second_claim is None
    assert state == "SUCCEEDED"
