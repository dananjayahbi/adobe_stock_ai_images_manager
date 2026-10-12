"""End-to-end tests for the seven-stage pipeline.

These drive the orchestrator and the stage API the way the operator's UI does:
stage a batch, advance it stage by stage, and assert the record lands in the
right state with the right artifacts on disk.

External services are stubbed (the LLM gateway, Tesseract, Upscayl) so the tests
pin *pipeline behaviour* rather than third-party availability.
"""

import io

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import ImageRecord, ImageStatus, PipelineStage
from services import jobs as jobs_module
from services.stage_registry import (
    ORDERED_STAGES,
    is_terminal,
    next_stage,
    serialize_registry,
    stage_name,
    stage_number,
)


@pytest.fixture()
def pipeline_env(db_session_factory, monkeypatch, tmp_path):
    """Wire the orchestrator's storage into tmp_path and return a helper bundle."""
    from config import settings
    from services import ocr_scanner, upscaler

    for attribute in (
        "INBOX_DIR",
        "THUMBNAILS_DIR",
        "READY_DIR",
        "REFINED_DIR",
        "UPSCALED_DIR",
    ):
        directory = tmp_path / attribute.lower()
        directory.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(settings, attribute, directory)

    monkeypatch.setattr(settings, "MAX_REFINE_PASSES", 3)
    monkeypatch.setattr(settings, "METADATA_CALL_DELAY_SECONDS", 0.0)

    # Tesseract is optional in this environment; stub it so the OCR stage is
    # deterministic. Individual tests override this with their own verdict.
    class _OcrStub:
        text_detected = False
        classification = "none"
        text = ""
        mean_confidence = 0.0
        word_count = 0
        reason = "No text detected (none)."
        blocked = False

        def to_dict(self):
            return {
                "text_detected": False,
                "classification": "none",
                "text": "",
                "mean_confidence": 0.0,
                "word_count": 0,
                "reason": self.reason,
                "blocked": False,
                "words": [],
            }

    monkeypatch.setattr(ocr_scanner, "scan_text", lambda path: _OcrStub())

    # Upscayl ships as a GUI app, so Stage 3 falls back to resampling. That is
    # real behaviour worth exercising, so only the CLI probe is pinned.
    monkeypatch.setattr(upscaler, "find_cli", lambda cfg=None: None)

    return {"settings": settings, "tmp_path": tmp_path, "factory": db_session_factory}


def _make_record(factory, tmp_path, *, name="sample.jpg", stage=PipelineStage.COLLECTED):
    """Persist a COLLECTED record backed by a real JPEG on disk."""
    from tests.test_acceptance_scorer import _noisy_gradient

    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / name

    import cv2

    image = _noisy_gradient(2400, 2000)
    cv2.imwrite(
        str(path),
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_CHROMA_QUALITY, 100],
    )

    db = factory()
    try:
        record = ImageRecord(
            filename=name,
            original_path=str(path),
            status=ImageStatus.PENDING,
            stage=stage,
            working_path=str(path),
            file_size_bytes=path.stat().st_size,
            megapixels=4.8,
            width=2400,
            height=2000,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        record_id = record.id
    finally:
        db.close()

    return record_id, path


def _reload(factory, record_id) -> ImageRecord:
    db = factory()
    try:
        record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
        assert record is not None
        # Detach a copy of the scalar state so assertions read cleanly.
        db.expunge(record)
        return record
    finally:
        db.close()


def _stub_semantic(monkeypatch, score=0.95, flags=None):
    from services import gemini_auditor

    monkeypatch.setattr(
        gemini_auditor,
        "audit_image",
        lambda path, api_key=None: {
            "passed": True,
            "confidence_score": score,
            "flags": flags or [],
            "reason": "",
        },
    )


def _stub_metadata(monkeypatch, title="Mountain ridge at golden hour"):
    from services import gemini_metadata

    monkeypatch.setattr(
        gemini_metadata,
        "generate_metadata",
        lambda *args, **kwargs: {
            "title": title,
            "description": "Layered peaks under warm evening light.",
            "keywords": ["mountains", "sunset", "landscape", "golden hour", "peaks"],
            "category": 11,
        },
    )


# --------------------------------------------------------------------------- #
# Stage registry
# --------------------------------------------------------------------------- #

def test_registry_exposes_seven_numbered_stages():
    registry = serialize_registry()

    assert len(registry) == 7
    assert [item["number"] for item in registry] == [1, 2, 3, 4, 5, 6, 7]
    assert registry[0]["key"] == "collector"
    assert registry[-1]["key"] == "gallery"
    assert registry[-1]["terminal"] is True


def test_stage_number_and_name_helpers():
    assert stage_number(PipelineStage.COLLECTED) == 1
    assert stage_number(PipelineStage.OCR_REJECTED) == 2
    assert stage_number(PipelineStage.PUBLISHED) == 7
    assert stage_name(PipelineStage.INCOMPATIBLE) == "Compatibility Check"


def test_terminal_stages_are_rejected_and_incompatible():
    assert is_terminal(PipelineStage.OCR_REJECTED) is True
    assert is_terminal(PipelineStage.INCOMPATIBLE) is True
    assert is_terminal(PipelineStage.COLLECTED) is False
    assert is_terminal(PipelineStage.PUBLISHED) is False


def test_next_stage_advances_and_stops_at_terminal():
    assert next_stage(PipelineStage.COLLECTED) == PipelineStage.OCR_CLEAR
    assert next_stage(PipelineStage.OCR_CLEAR) == PipelineStage.UPSCALED
    assert next_stage(PipelineStage.METADATA_READY) == PipelineStage.PUBLISHED
    # A rejected image must not advance into the upscale stage.
    assert next_stage(PipelineStage.OCR_REJECTED) is None


def test_ordered_stages_cover_every_stage():
    # QUARANTINED is deliberately off-flow: set aside by the diversity gate,
    # it belongs to no numbered stage and is terminal.
    from services.stage_registry import TERMINAL_STAGES

    off_flow = {PipelineStage.QUARANTINED}
    assert set(ORDERED_STAGES) == set(PipelineStage) - off_flow
    assert off_flow <= TERMINAL_STAGES


# --------------------------------------------------------------------------- #
# Stage 2 - OCR
# --------------------------------------------------------------------------- #

def test_ocr_stage_marks_clean_images_ocr_clear(pipeline_env, monkeypatch):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(pipeline_env["factory"], pipeline_env["tmp_path"])

    job_id = stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    job = jobs_module.registry.get(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.succeeded == 1

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.OCR_CLEAR


def test_ocr_stage_rejects_images_with_text(pipeline_env, monkeypatch):
    from services import ocr_scanner
    from tasks import stage_orchestrator

    class _Blocked:
        text_detected = True
        classification = "embedded_text"
        text = "SALE 50% OFF"
        mean_confidence = 88.0
        word_count = 3
        reason = "Readable text detected in the image: 'SALE 50% OFF'"
        blocked = True

        def to_dict(self):
            return {
                "text_detected": True,
                "classification": "embedded_text",
                "text": self.text,
                "mean_confidence": self.mean_confidence,
                "word_count": self.word_count,
                "reason": self.reason,
                "blocked": True,
                "words": [],
            }

    monkeypatch.setattr(ocr_scanner, "scan_text", lambda path: _Blocked())

    record_id, _ = _make_record(pipeline_env["factory"], pipeline_env["tmp_path"])
    stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.OCR_REJECTED
    # A text-bearing image must not sit in the PASSED queue.
    assert record.status == ImageStatus.FLAGGED
    assert record.ocr_text_detected is True


def test_ocr_stage_skips_already_scanned_records(pipeline_env):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.OCR_CLEAR,
    )

    job_id = stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    job = jobs_module.registry.get(job_id)
    assert job.skipped == 1
    assert "Already scanned" in job.items[0].message


def test_rejected_image_does_not_advance_to_upscale(pipeline_env):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.OCR_REJECTED,
    )

    stage_orchestrator.run_upscale_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.OCR_REJECTED


# --------------------------------------------------------------------------- #
# Stage 3 - Upscale
# --------------------------------------------------------------------------- #

def test_upscale_stage_produces_a_working_copy(pipeline_env):
    from tasks import stage_orchestrator

    record_id, original = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.OCR_CLEAR,
    )

    stage_orchestrator.run_upscale_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.UPSCALED
    assert record.working_path is not None
    assert record.working_path != str(original)
    # The resample fallback must produce a genuinely larger image.
    from pathlib import Path

    with Image.open(record.working_path) as upscaled:
        assert max(upscaled.size) > 2400


def test_upscale_stage_records_which_backend_ran(pipeline_env):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.OCR_CLEAR,
    )

    stage_orchestrator.run_upscale_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    detail = (record.stage_details or {}).get("upscale", {})
    # The UI must not imply a neural upscale that never happened.
    assert detail.get("backend") in ("lanczos-resample", "upscaled", "skipped")
    assert "success" in detail


# --------------------------------------------------------------------------- #
# Stage 4 - Refine
# --------------------------------------------------------------------------- #

def test_refine_stage_writes_a_refined_copy_and_scores_it(pipeline_env, monkeypatch):
    from tasks import stage_orchestrator

    _stub_semantic(monkeypatch)
    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.UPSCALED,
    )

    stage_orchestrator.run_refine_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.REFINED
    assert record.acceptance_score is not None
    assert 0.0 <= record.acceptance_score <= 1.0
    assert record.acceptance_report is not None
    assert "refine" in (record.stage_details or {})


def test_refine_stage_without_semantic_still_scores(pipeline_env):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.UPSCALED,
    )

    stage_orchestrator.run_refine_stage(
        pipeline_env["factory"],
        [record_id],
        pipeline_env["settings"],
        use_semantic=False,
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.REFINED
    assert record.acceptance_score is not None


# --------------------------------------------------------------------------- #
# Stage 5 - Compatibility gate
# --------------------------------------------------------------------------- #

def test_compatibility_stage_passes_a_clean_image(pipeline_env, monkeypatch):
    from tasks import stage_orchestrator

    _stub_semantic(monkeypatch)
    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.REFINED,
    )

    stage_orchestrator.run_compatibility_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.COMPATIBLE
    # Passing the gate must make the record approvable by the existing flow.
    assert record.status == ImageStatus.PASSED


def test_compatibility_stage_flags_a_damaged_image(pipeline_env, monkeypatch):
    import cv2

    from tasks import stage_orchestrator

    # A perfectly flat frame cannot reach 80% no matter how it is tweaked.
    flat = pipeline_env["tmp_path"] / "inbox" / "flat.jpg"
    flat.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(flat), __import__("numpy").full((2000, 2400, 3), 128, "uint8"))

    factory = pipeline_env["factory"]
    db = factory()
    try:
        record = ImageRecord(
            filename="flat.jpg",
            original_path=str(flat),
            status=ImageStatus.PENDING,
            stage=PipelineStage.REFINED,
            working_path=str(flat),
            file_size_bytes=flat.stat().st_size,
            width=2400,
            height=2000,
            megapixels=4.8,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        record_id = record.id
    finally:
        db.close()

    _stub_semantic(monkeypatch, score=0.15, flags=["synthetic texture"])
    stage_orchestrator.run_compatibility_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(factory, record_id)
    assert record.stage == PipelineStage.INCOMPATIBLE
    assert record.status == ImageStatus.FLAGGED
    # The failure must carry actionable advice, not just a number.
    detail = (record.stage_details or {}).get("compatibility", {})
    assert detail.get("remediation")


# --------------------------------------------------------------------------- #
# Stage 6 - Metadata
# --------------------------------------------------------------------------- #

def test_metadata_stage_generates_and_persists_metadata(pipeline_env, monkeypatch):
    from tasks import stage_orchestrator

    _stub_metadata(monkeypatch)
    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.COMPATIBLE,
    )

    stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.METADATA_READY
    assert record.generated_title == "Mountain ridge at golden hour"
    assert record.generated_keywords
    assert record.category == 11


def test_metadata_stage_survives_a_model_failure(pipeline_env, monkeypatch):
    from services import gemini_metadata
    from tasks import stage_orchestrator

    monkeypatch.setattr(
        gemini_metadata, "generate_metadata", lambda *args, **kwargs: None
    )

    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.COMPATIBLE,
    )

    job_id = stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    job = jobs_module.registry.get(job_id)
    assert job.failed == 1
    # A failed item must leave the record where it was, not advance it.
    record = _reload(pipeline_env["factory"], record_id)
    assert record.stage == PipelineStage.COMPATIBLE


def test_metadata_stage_processes_records_sequentially(pipeline_env, monkeypatch):
    """Calls must be serialized to avoid tripping upstream rate limits."""
    from services import gemini_metadata
    from tasks import stage_orchestrator

    order: list[str] = []

    def recording_generate(*args, **kwargs):
        order.append(str(args[0]))
        return {
            "title": f"Title {len(order)}",
            "description": "d",
            "keywords": ["a", "b"],
            "category": 8,
        }

    monkeypatch.setattr(gemini_metadata, "generate_metadata", recording_generate)

    ids = [
        _make_record(
            pipeline_env["factory"],
            pipeline_env["tmp_path"],
            name=f"img{i}.jpg",
            stage=PipelineStage.COMPATIBLE,
        )[0]
        for i in range(3)
    ]

    stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], ids, pipeline_env["settings"]
    )

    assert len(order) == 3
    for record_id in ids:
        assert _reload(pipeline_env["factory"], record_id).stage == PipelineStage.METADATA_READY


def test_metadata_stage_skips_terminal_records(pipeline_env, monkeypatch):
    from tasks import stage_orchestrator

    _stub_metadata(monkeypatch)
    record_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        stage=PipelineStage.OCR_REJECTED,
    )

    job_id = stage_orchestrator.run_metadata_stage(
        pipeline_env["factory"], [record_id], pipeline_env["settings"]
    )

    job = jobs_module.registry.get(job_id)
    assert job.skipped == 1


# --------------------------------------------------------------------------- #
# Stage 6 - CSV from the database
# --------------------------------------------------------------------------- #

def test_build_metadata_csv_includes_only_ready_stages(pipeline_env):
    from tasks import stage_orchestrator

    ready_id, _ = _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        name="ready.jpg",
        stage=PipelineStage.METADATA_READY,
    )
    _make_record(
        pipeline_env["factory"],
        pipeline_env["tmp_path"],
        name="collected.jpg",
        stage=PipelineStage.COLLECTED,
    )

    factory = pipeline_env["factory"]
    db = factory()
    try:
        record = db.query(ImageRecord).filter(ImageRecord.id == ready_id).first()
        record.generated_title = "A ready asset"
        record.generated_keywords = ["a", "b"]
        record.category = 11
        db.commit()
    finally:
        db.close()

    result = stage_orchestrator.build_metadata_csv(factory)

    assert result.row_count == 1
    assert "A ready asset" in result.csv_text
    # The COLLECTED image has no metadata yet and must not appear.
    assert "collected.jpg" not in result.csv_text


def test_build_metadata_csv_accepts_explicit_ids(pipeline_env):
    from tasks import stage_orchestrator

    ids = [
        _make_record(
            pipeline_env["factory"],
            pipeline_env["tmp_path"],
            name=f"asset{i}.jpg",
            stage=PipelineStage.PUBLISHED,
        )[0]
        for i in range(3)
    ]

    result = stage_orchestrator.build_metadata_csv(
        pipeline_env["factory"], [ids[0]], only_ready=True
    )

    assert result.row_count == 1


# --------------------------------------------------------------------------- #
# Batch reporting and cancellation
# --------------------------------------------------------------------------- #

def test_batch_reports_missing_ids(pipeline_env):
    from tasks import stage_orchestrator

    record_id, _ = _make_record(pipeline_env["factory"], pipeline_env["tmp_path"])

    job_id = stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"],
        [record_id, "does-not-exist"],
        pipeline_env["settings"],
    )

    job = jobs_module.registry.get(job_id)
    assert "not found" in job.message
    assert job.total == 1


def test_job_tracks_progress_and_totals(pipeline_env):
    from tasks import stage_orchestrator

    ids = [
        _make_record(
            pipeline_env["factory"], pipeline_env["tmp_path"], name=f"b{i}.jpg"
        )[0]
        for i in range(4)
    ]

    job_id = stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"], ids, pipeline_env["settings"]
    )
    job = jobs_module.registry.get(job_id)

    assert job.total == 4
    assert job.processed == 4
    assert job.progress == pytest.approx(1.0)
    assert job.status == "completed"
    assert len(job.items) == 4


def test_cancelled_batch_skips_remaining_records(pipeline_env, monkeypatch):
    from services import ocr_scanner
    from tasks import stage_orchestrator

    ids = [
        _make_record(
            pipeline_env["factory"], pipeline_env["tmp_path"], name=f"c{i}.jpg"
        )[0]
        for i in range(3)
    ]

    # Cancel the job from inside the first OCR call, mimicking the UI's
    # cancel button arriving mid-batch.
    original = ocr_scanner.scan_text

    def cancel_after_first(path):
        for job in jobs_module.registry.list_recent(5):
            if job.status == "running":
                job.cancel_requested = True
        return original(path)

    monkeypatch.setattr(ocr_scanner, "scan_text", cancel_after_first)

    job_id = stage_orchestrator.run_ocr_stage(
        pipeline_env["factory"], ids, pipeline_env["settings"]
    )

    job = jobs_module.registry.get(job_id)
    assert job.status == "cancelled"
    assert job.skipped >= 1
    # The records that were skipped must not have advanced.
    remaining = [
        _reload(pipeline_env["factory"], rid).stage for rid in ids
    ]
    assert PipelineStage.COLLECTED in remaining
