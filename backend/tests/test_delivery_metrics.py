"""Round 3: the reported geometry must describe the file that is delivered.

The operator reported "all image dimensions shrunk to 1366x768 when I published".
Nothing shrank — the delivered files were 3840x2143 — but the gallery *displayed*
the inbox original's dimensions, because `width`/`height`/`megapixels`/
`file_size_bytes` were measured once at ingestion and never refreshed after the
upscale, refine or conversion replaced the working copy.

That is not cosmetic. `low_resolution` is a **critical** acceptance issue scored
from the megapixels, so a stale 1.06 MP claimed a below-Adobe-floor resolution
for an asset that comfortably passes.

The search and stage filters are pinned here too, since they share the same
endpoint and the same class of risk: a filter that silently matches nothing looks
identical to a broken control.
"""

import pytest
from PIL import Image

from models import PipelineStage
from services import record_metrics
from tests.test_stage_pipeline import pipeline_env  # noqa: F401  (shared fixture)


def _write_jpeg(path, size, quality=90):
    """Write a real JPEG of the given size so Pillow can measure it back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(90, 120, 150)).save(path, "JPEG", quality=quality)
    return path


@pytest.fixture()
def make_record(db_session_factory):
    """Insert a record directly, since the metrics layer only reads fields."""

    def _make(
        filename: str = "img.jpg",
        *,
        stage: PipelineStage = PipelineStage.METADATA_READY,
        original_path: str = "/tmp/missing.jpg",
        working_path: str | None = None,
        width: int | None = None,
        height: int | None = None,
        megapixels: float | None = None,
        file_size_bytes: int = 1024,
        title: str | None = None,
        description: str | None = None,
        keywords: list[str] | None = None,
        category: int | None = None,
        download_name: str | None = None,
        suggested_filename: str | None = None,
    ) -> str:
        from models import ImageRecord

        session = db_session_factory()
        record = ImageRecord(
            filename=filename,
            original_path=original_path,
            file_size_bytes=file_size_bytes,
            stage=stage,
            working_path=working_path,
            width=width,
            height=height,
            megapixels=megapixels,
            generated_title=title,
            generated_description=description,
            generated_keywords=keywords,
            category=category,
            download_name=download_name,
            suggested_filename=suggested_filename,
        )
        session.add(record)
        session.commit()
        record_id = record.id
        session.close()
        return record_id

    return _make


def _reload(db_session_factory, record_id):
    from models import ImageRecord

    session = db_session_factory()
    try:
        return session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Delivered path resolution
# --------------------------------------------------------------------------- #

def test_delivered_path_prefers_the_working_copy(tmp_path, make_record, db_session_factory):
    """The measurement must describe the file the operator receives."""
    original = _write_jpeg(tmp_path / "inbox" / "a.jpg", (1376, 768))
    working = _write_jpeg(tmp_path / "upscaled" / "a.jpg", (3840, 2143))

    record_id = make_record(
        original_path=str(original), working_path=str(working)
    )
    record = _reload(db_session_factory, record_id)

    assert record_metrics.delivered_path(record) == working


def test_delivered_path_prefers_the_staged_file_once_published(
    tmp_path, make_record, db_session_factory, monkeypatch
):
    """Once published, the staged copy *is* the deliverable - not the working one."""
    from config import settings

    ready_dir = tmp_path / "ready"
    ready_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "READY_DIR", ready_dir)

    working = _write_jpeg(tmp_path / "refined" / "a.jpg", (2000, 1000))
    record_id = make_record(working_path=str(working))
    staged = _write_jpeg(ready_dir / f"{record_id}.jpg", (3840, 2143))

    record = _reload(db_session_factory, record_id)

    assert record_metrics.delivered_path(record) == staged


def test_delivered_path_falls_back_to_the_original(tmp_path, make_record, db_session_factory):
    """A collected record with no working copy is its own deliverable."""
    original = _write_jpeg(tmp_path / "inbox" / "b.jpg", (1200, 800))
    record_id = make_record(original_path=str(original))
    record = _reload(db_session_factory, record_id)

    assert record_metrics.delivered_path(record) == original


def test_delivered_path_is_none_when_nothing_exists(make_record, db_session_factory):
    record_id = make_record(original_path="/tmp/definitely-not-here.jpg")
    record = _reload(db_session_factory, record_id)

    assert record_metrics.delivered_path(record) is None


# --------------------------------------------------------------------------- #
# The refresh itself
# --------------------------------------------------------------------------- #

def test_refresh_measures_the_delivered_file_not_the_original(
    tmp_path, make_record, db_session_factory
):
    """The exact reported bug, stated as a test.

    Before the fix the record kept the original's 1376x768 forever, so a
    published 8.2 MP asset reported 1.06 MP.
    """
    original = _write_jpeg(tmp_path / "inbox" / "c.jpg", (1376, 768))
    working = _write_jpeg(tmp_path / "upscaled" / "c.jpg", (3840, 2143))

    record_id = make_record(
        original_path=str(original),
        working_path=str(working),
        width=1376,
        height=768,
        megapixels=1.06,
    )
    record = _reload(db_session_factory, record_id)

    measured = record_metrics.refresh_delivery_metrics(record)

    assert measured["width"] == 3840
    assert measured["height"] == 2143
    assert measured["megapixels"] == pytest.approx(8.2291, abs=0.001)
    assert record.width == 3840
    assert record.height == 2143
    assert record.megapixels == pytest.approx(8.2291, abs=0.001)
    # The byte size was wrong in the same way: the staged file is much larger.
    assert record.file_size_bytes == working.stat().st_size
    assert record.file_size_bytes > original.stat().st_size


def test_refresh_records_which_file_was_measured(
    tmp_path, make_record, db_session_factory
):
    """Without provenance, a later reader cannot tell the two apart."""
    working = _write_jpeg(tmp_path / "upscaled" / "d.jpg", (3840, 2143))
    record_id = make_record(working_path=str(working))
    record = _reload(db_session_factory, record_id)

    record_metrics.refresh_delivery_metrics(record)

    details = record.stage_details or {}
    assert details["metrics"]["measured_path"] == str(working)
    assert details["metrics"]["width"] == 3840


def test_refresh_leaves_values_alone_when_nothing_can_be_measured(
    make_record, db_session_factory
):
    """A wrong number is worse than a stale one that was once true."""
    record_id = make_record(
        original_path="/tmp/nope.jpg", width=2000, height=1000, megapixels=2.0
    )
    record = _reload(db_session_factory, record_id)

    assert record_metrics.refresh_delivery_metrics(record) is None
    assert record.width == 2000
    assert record.height == 1000
    assert record.megapixels == 2.0


def test_refresh_survives_an_unreadable_file(tmp_path, make_record, db_session_factory):
    """A corrupt file must not break the pipeline that is measuring it."""
    broken = tmp_path / "upscaled" / "broken.jpg"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_bytes(b"not actually a jpeg")

    record_id = make_record(working_path=str(broken), width=100, height=100)
    record = _reload(db_session_factory, record_id)

    assert record_metrics.refresh_delivery_metrics(record) is None
    assert record.width == 100


# --------------------------------------------------------------------------- #
# The pipeline refreshes it
# --------------------------------------------------------------------------- #

def test_upscale_stage_refreshes_the_reported_dimensions(
    pipeline_env, monkeypatch, tmp_path
):
    """The end-to-end path: upscale, then read the record back."""
    from models import ImageRecord
    from services import upscaler
    from tasks import stage_orchestrator
    from tests.test_stage_pipeline import _make_record

    upscaled = _write_jpeg(tmp_path / "upscaled-out.jpg", (3840, 2143))

    class _Result:
        success = True
        output_path = str(upscaled)
        backend = "vulkan"
        reason = ""
        model = "4xNomos8kSC"
        source_megapixels = 1.06
        output_megapixels = 8.23

        def to_dict(self):
            return {"backend": self.backend, "model": self.model}

    monkeypatch.setattr(upscaler, "upscale_image", lambda *a, **k: _Result())

    record_id, _ = _make_record(
        pipeline_env["factory"], pipeline_env["tmp_path"], stage=PipelineStage.OCR_CLEAR
    )

    stage_orchestrator.run_upscale_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    session = pipeline_env["factory"]()
    try:
        record = session.query(ImageRecord).filter(ImageRecord.id == record_id).first()
        assert record.working_path == str(upscaled)
        # The whole point: the reported geometry follows the new file.
        assert record.width == 3840
        assert record.height == 2143
        assert record.megapixels == pytest.approx(8.2291, abs=0.001)
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Startup repair
# --------------------------------------------------------------------------- #

def test_repair_fixes_stale_metrics_and_is_idempotent(
    tmp_path, make_record, db_session_factory
):
    """Existing records must be corrected, and a second pass must do nothing."""
    from services.metric_repair import repair_delivery_metrics

    working = _write_jpeg(tmp_path / "upscaled" / "e.jpg", (3840, 2143))
    record_id = make_record(
        stage=PipelineStage.PUBLISHED,
        working_path=str(working),
        width=1376,
        height=768,
        megapixels=1.06,
        file_size_bytes=999,
    )

    assert repair_delivery_metrics(db_session_factory) == 1

    record = _reload(db_session_factory, record_id)
    assert record.width == 3840
    assert record.megapixels == pytest.approx(8.2291, abs=0.001)

    # Second run: the numbers now agree with the file, so nothing is touched.
    assert repair_delivery_metrics(db_session_factory) == 0


def test_repair_skips_a_record_whose_metrics_already_match(
    tmp_path, make_record, db_session_factory
):
    from services.metric_repair import repair_delivery_metrics

    working = _write_jpeg(tmp_path / "upscaled" / "f.jpg", (1200, 900))
    make_record(
        stage=PipelineStage.PUBLISHED,
        working_path=str(working),
        width=1200,
        height=900,
        megapixels=1.08,
        file_size_bytes=working.stat().st_size,
    )

    assert repair_delivery_metrics(db_session_factory) == 0


def test_repair_ignores_records_whose_deliverable_is_the_original(
    tmp_path, make_record, db_session_factory
):
    """A COLLECTED record has no working copy, so there is nothing to correct.

    Re-measuring it would be wasted startup work on every boot, which is why the
    stage filter exists rather than checking every row.
    """
    from services.metric_repair import repair_delivery_metrics

    original = _write_jpeg(tmp_path / "inbox" / "g.jpg", (1500, 1000))
    record_id = make_record(
        stage=PipelineStage.COLLECTED,
        original_path=str(original),
        width=1500,
        height=1000,
        megapixels=1.5,
        file_size_bytes=original.stat().st_size,
    )

    assert repair_delivery_metrics(db_session_factory) == 0
    assert _reload(db_session_factory, record_id).width == 1500


# --------------------------------------------------------------------------- #
# Stage + search filters
# --------------------------------------------------------------------------- #

def test_stage_filter_selects_only_the_requested_stages(client, make_record):
    published = make_record("a.jpg", stage=PipelineStage.PUBLISHED, title="Published One")
    make_record("b.jpg", stage=PipelineStage.METADATA_READY, title="Draft One")

    body = client.get("/api/records", params={"stage": "PUBLISHED"}).json()

    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [published]


def test_stage_filter_accepts_several_stages(client, make_record):
    make_record("a.jpg", stage=PipelineStage.PUBLISHED)
    make_record("b.jpg", stage=PipelineStage.METADATA_READY)
    make_record("c.jpg", stage=PipelineStage.OCR_REJECTED)

    body = client.get(
        "/api/records", params={"stage": "PUBLISHED,METADATA_READY"}
    ).json()

    assert body["total"] == 2


def test_stage_filter_reports_an_invalid_stage(client):
    """A typo must be reported, not silently match nothing.

    A filter that returns zero rows for a misspelled value is indistinguishable
    from a filter that is broken, which is the harder bug to find.
    """
    response = client.get("/api/records", params={"stage": "PUBLISHEDX"})

    assert response.status_code == 400
    assert "PUBLISHEDX" in response.json()["detail"]


def test_search_matches_the_generated_title(client, make_record):
    make_record("a.jpg", title="Autonomous warehouse robots")
    make_record("b.jpg", title="Yellow scissor lift")

    body = client.get("/api/records", params={"search": "warehouse"}).json()

    assert body["total"] == 1
    assert body["items"][0]["generated_title"] == "Autonomous warehouse robots"


def test_search_is_case_insensitive(client, make_record):
    make_record("a.jpg", title="Autonomous Warehouse Robots")

    assert client.get("/api/records", params={"search": "WAREHOUSE"}).json()["total"] == 1
    assert client.get("/api/records", params={"search": "wArEhOuSe"}).json()["total"] == 1


def test_search_matches_a_keyword_not_in_the_title(client, make_record):
    """The case a title-only search would miss.

    The operator remembers an image by a keyword that never made it into the
    title, which is the most likely reason to reach for search at all.
    """
    make_record(
        "a.jpg",
        title="Industrial interior",
        keywords=["intralogistics", "pallet"],
    )
    make_record("b.jpg", title="Industrial exterior", keywords=["sky"])

    body = client.get("/api/records", params={"search": "intralogistics"}).json()

    assert body["total"] == 1
    assert body["items"][0]["filename"] == "a.jpg"


def test_search_matches_the_delivered_filename(client, make_record):
    """The name the operator set for the upload must be searchable."""
    make_record("a.jpg", title="Ignored", download_name="chosen-upload-name.jpg")
    make_record("b.jpg", title="Other")

    body = client.get("/api/records", params={"search": "chosen-upload"}).json()

    assert body["total"] == 1


def test_search_matches_the_description(client, make_record):
    make_record("a.jpg", description="A quiet forest clearing at dawn")
    make_record("b.jpg", description="A busy city street")

    body = client.get("/api/records", params={"search": "forest clearing"}).json()

    assert body["total"] == 1


def test_search_combines_with_the_stage_filter(client, make_record):
    """Filters compose; a search must not escape the current scope."""
    make_record("a.jpg", stage=PipelineStage.PUBLISHED, title="Warehouse robots")
    make_record("b.jpg", stage=PipelineStage.METADATA_READY, title="Warehouse robots")

    body = client.get(
        "/api/records", params={"stage": "PUBLISHED", "search": "warehouse"}
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["stage"] == "PUBLISHED"


def test_search_rejects_an_overlong_term(client):
    """A search is a UI affordance, not an unbounded pattern scan."""
    response = client.get("/api/records", params={"search": "x" * 201})

    assert response.status_code == 400
    assert "200" in response.json()["detail"]


def test_blank_search_does_not_filter(client, make_record):
    """Clearing the box must restore the full list, not match the empty string."""
    make_record("a.jpg", title="One")
    make_record("b.jpg", title="Two")

    assert client.get("/api/records", params={"search": ""}).json()["total"] == 2
    assert client.get("/api/records", params={"search": "   "}).json()["total"] == 2
