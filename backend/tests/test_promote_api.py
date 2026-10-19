"""Tests for the gallery's manual "push to ready-to-upload" override.

The contract under test: the pre-flight check reports which of the three
requirements (acceptance QC, sRGB profile, metadata) each record is missing
without touching anything, and the run endpoint executes ONLY those gaps
before moving a record to METADATA_READY. OCR_REJECTED is never promotable.
"""

from __future__ import annotations

import io

from PIL import Image
from sqlalchemy.orm import sessionmaker

from models import ImageRecord, ImageStatus, PipelineStage


def _jpeg(path, *, tagged: bool = False):
    image = Image.new("RGB", (64, 64), (200, 60, 60))
    if tagged:
        from services.srgb_profile import srgb_profile_bytes

        image.save(path, "JPEG", quality=90, icc_profile=srgb_profile_bytes())
    else:
        image.save(path, "JPEG", quality=90)
    return path


def _make_record(db, tmp_path, **overrides) -> str:
    source = _jpeg(tmp_path / f"{overrides.get('filename', 'img')}.jpg")
    record = ImageRecord(
        filename=overrides.get("filename", "img.jpg"),
        original_path=str(source),
        working_path=str(source),
        status=ImageStatus.PENDING,
        stage=overrides.get("stage", PipelineStage.QUARANTINED),
        file_size_bytes=source.stat().st_size,
        width=64,
        height=64,
        acceptance_report=overrides.get("acceptance_report"),
        acceptance_score=overrides.get("acceptance_score"),
        generated_title=overrides.get("generated_title"),
        generated_keywords=overrides.get("generated_keywords"),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record.id


PASSING_REPORT = {"passed": True, "score": 0.91}


class TestPromoteCheck:
    def test_check_reports_missing_steps(self, client, db_session_factory, tmp_path):
        db = db_session_factory()
        try:
            record_id = _make_record(db, tmp_path)  # quarantined, nothing done
        finally:
            db.close()

        response = client.post(
            "/api/promote/check", json={"record_ids": [record_id]}
        )
        assert response.status_code == 200, response.text
        item = response.json()["items"][0]
        assert item["eligible"] is True
        by_key = {step["key"]: step for step in item["steps"]}
        assert by_key["acceptance"]["ok"] is False
        assert by_key["srgb"]["ok"] is False
        assert by_key["metadata"]["ok"] is False

    def test_check_recognises_satisfied_steps(
        self, client, db_session_factory, tmp_path
    ):
        db = db_session_factory()
        try:
            source = _jpeg(tmp_path / "tagged.jpg", tagged=True)
            record = ImageRecord(
                filename="tagged.jpg",
                original_path=str(source),
                working_path=str(source),
                status=ImageStatus.PASSED,
                stage=PipelineStage.COMPATIBLE,
                file_size_bytes=source.stat().st_size,
                width=64,
                height=64,
                acceptance_report=PASSING_REPORT,
                acceptance_score=0.91,
                generated_title="A title",
                generated_keywords=["a", "b"],
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        item = client.post(
            "/api/promote/check", json={"record_ids": [record_id]}
        ).json()["items"][0]
        by_key = {step["key"]: step for step in item["steps"]}
        assert by_key["acceptance"]["ok"] is True
        assert by_key["srgb"]["ok"] is True
        assert by_key["metadata"]["ok"] is True

    def test_ocr_rejected_is_not_eligible(
        self, client, db_session_factory, tmp_path
    ):
        db = db_session_factory()
        try:
            record_id = _make_record(
                db, tmp_path, stage=PipelineStage.OCR_REJECTED
            )
        finally:
            db.close()

        item = client.post(
            "/api/promote/check", json={"record_ids": [record_id]}
        ).json()["items"][0]
        assert item["eligible"] is False
        assert "OCR" in item["blocker"]

    def test_empty_ids_rejected(self, client):
        response = client.post("/api/promote/check", json={"record_ids": []})
        assert response.status_code == 400


class TestPromoteRun:
    def _run(self, client, db_session_factory, record_ids, monkeypatch):
        # The endpoint dispatches through `routers.promote.SessionLocal`;
        # point it at the test's in-memory factory (the real module global
        # would silently operate on the developer's database).
        import routers.promote as promote_router

        monkeypatch.setattr(promote_router, "SessionLocal", db_session_factory)
        response = client.post(
            "/api/promote/run", json={"record_ids": record_ids, "use_semantic": False}
        )
        assert response.status_code == 200, response.text
        job_id = response.json()["id"]
        # BackgroundTasks runs eagerly under TestClient.
        return client.get(f"/api/jobs/{job_id}").json()

    def test_run_promotes_with_missing_metadata_only(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        """Acceptance + sRGB already pass → only metadata runs, then promote."""
        from services import gemini_metadata

        calls = {"metadata": 0}

        def fake_generate(path, **kwargs):
            calls["metadata"] += 1
            return {
                "title": "Generated title",
                "description": "Generated description",
                "keywords": ["one", "two"],
                "category": 10,
            }

        monkeypatch.setattr(gemini_metadata, "generate_metadata", fake_generate)

        db = db_session_factory()
        try:
            source = _jpeg(tmp_path / "ready.jpg", tagged=True)
            record = ImageRecord(
                filename="ready.jpg",
                original_path=str(source),
                working_path=str(source),
                status=ImageStatus.PENDING,
                stage=PipelineStage.COMPATIBLE,
                file_size_bytes=source.stat().st_size,
                width=64,
                height=64,
                acceptance_report=PASSING_REPORT,
                acceptance_score=0.91,
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        job = self._run(client, db_session_factory, [record_id], monkeypatch)
        assert job["status"] == "completed"
        assert job["succeeded"] == 1
        assert calls["metadata"] == 1  # metadata was the only gap

        db = db_session_factory()
        try:
            record = db.get(ImageRecord, record_id)
            assert record.stage == PipelineStage.METADATA_READY
            assert record.generated_title == "Generated title"
            assert (record.stage_details or {}).get("promote")
        finally:
            db.close()

    def test_run_skips_steps_that_already_pass(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        """Nothing missing → no step runs at all; the record just moves."""
        from services import compatibility_checker, gemini_metadata

        monkeypatch.setattr(
            gemini_metadata,
            "generate_metadata",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
        )
        monkeypatch.setattr(
            compatibility_checker,
            "check_compatibility",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")),
        )

        db = db_session_factory()
        try:
            source = _jpeg(tmp_path / "done.jpg", tagged=True)
            record = ImageRecord(
                filename="done.jpg",
                original_path=str(source),
                working_path=str(source),
                status=ImageStatus.PENDING,
                stage=PipelineStage.COMPATIBLE,
                file_size_bytes=source.stat().st_size,
                width=64,
                height=64,
                acceptance_report=PASSING_REPORT,
                acceptance_score=0.91,
                generated_title="Title",
                generated_keywords=["x"],
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        job = self._run(client, db_session_factory, [record_id], monkeypatch)
        assert job["succeeded"] == 1
        assert "skipped" in job["items"][0]["message"].lower()

        db = db_session_factory()
        try:
            assert db.get(ImageRecord, record_id).stage == PipelineStage.METADATA_READY
        finally:
            db.close()

    def test_run_embeds_missing_srgb_and_promotes(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        """Untagged file, passing QC, no metadata → sRGB embed runs for real."""
        from config import settings
        from services import gemini_metadata
        from services.srgb_profile import has_srgb_profile

        srgb_dir = tmp_path / "srgb"
        monkeypatch.setattr(settings, "SRGB_DIR", srgb_dir)
        monkeypatch.setattr(
            gemini_metadata,
            "generate_metadata",
            lambda *a, **k: {
                "title": "T",
                "description": "D",
                "keywords": ["k"],
                "category": 3,
            },
        )

        db = db_session_factory()
        try:
            source = _jpeg(tmp_path / "untagged.jpg")  # no ICC profile
            record = ImageRecord(
                filename="untagged.jpg",
                original_path=str(source),
                working_path=str(source),
                status=ImageStatus.PENDING,
                stage=PipelineStage.COMPATIBLE,
                file_size_bytes=source.stat().st_size,
                width=64,
                height=64,
                acceptance_report=PASSING_REPORT,
                acceptance_score=0.91,
            )
            db.add(record)
            db.commit()
            record_id = record.id
        finally:
            db.close()

        job = self._run(client, db_session_factory, [record_id], monkeypatch)
        assert job["succeeded"] == 1, job["items"][0]["message"]

        db = db_session_factory()
        try:
            record = db.get(ImageRecord, record_id)
            assert record.stage == PipelineStage.METADATA_READY
            assert record.working_path.startswith(str(srgb_dir))
            assert has_srgb_profile(record.working_path)
            assert (record.stage_details or {}).get("embed_srgb", {}).get("ok")
        finally:
            db.close()

    def test_failed_acceptance_does_not_promote(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        """A record whose QC fails stays put; the report is stored for the UI."""
        from services import compatibility_checker
        from services.acceptance.types import AcceptanceReport, Issue

        failing = compatibility_checker.CompatibilityResult(
            passed=False,
            report=AcceptanceReport(
                score=0.42,
                threshold=0.8,
                passed=False,
                sub_scores={},
                issues=[
                    Issue(
                        code="soft_focus",
                        severity="major",
                        detail="Too soft.",
                    )
                ],
                metrics={},
            ),
            remediation=["Sharpen."],
            summary="Below threshold - score 42.0% (needs 80%).",
        )
        monkeypatch.setattr(
            compatibility_checker, "check_compatibility", lambda *a, **k: failing
        )

        db = db_session_factory()
        try:
            record_id = _make_record(db, tmp_path)  # no report yet
        finally:
            db.close()

        job = self._run(client, db_session_factory, [record_id], monkeypatch)
        assert job["failed"] == 1

        db = db_session_factory()
        try:
            record = db.get(ImageRecord, record_id)
            assert record.stage == PipelineStage.QUARANTINED  # unchanged
            assert record.acceptance_report and not record.acceptance_report["passed"]
        finally:
            db.close()

    def test_ocr_rejected_is_skipped(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        db = db_session_factory()
        try:
            record_id = _make_record(
                db, tmp_path, stage=PipelineStage.OCR_REJECTED
            )
        finally:
            db.close()

        job = self._run(client, db_session_factory, [record_id], monkeypatch)
        assert job["skipped"] == 1

        db = db_session_factory()
        try:
            record = db.get(ImageRecord, record_id)
            assert record.stage == PipelineStage.OCR_REJECTED
        finally:
            db.close()


class TestAuditorProvenanceFilter:
    def test_prompt_forbids_ai_provenance_judgement(self):
        from services.gemini_auditor import AUDIT_PROMPT

        assert "NEVER" in AUDIT_PROMPT
        assert "AI-generated" in AUDIT_PROMPT

    def test_provenance_flags_are_dropped(self, monkeypatch, tmp_path):
        from services import gemini_auditor
        from services.llm_client import LLMError  # noqa: F401  (documents the interface)

        def fake_chat_json(path, prompt, temperature=0.1):
            return {
                "confidence_score": 0.9,
                "flags": [
                    "Image is likely AI-generated",
                    "Overall saturation 0.47 is above the natural range.",
                    "Looks like AI art.",
                ],
                "is_commercially_viable": True,
            }

        monkeypatch.setattr(gemini_auditor, "chat_json", fake_chat_json)
        image = tmp_path / "x.jpg"
        _jpeg(image)

        result = gemini_auditor.audit_image(image)
        assert result["passed"] is True
        assert result["flags"] == [
            "Overall saturation 0.47 is above the natural range."
        ]

    def test_actionable_flags_survive(self, monkeypatch, tmp_path):
        from services import gemini_auditor

        def fake_chat_json(path, prompt, temperature=0.1):
            return {
                "confidence_score": 0.5,
                "flags": ["Artificial lighting cast on skin."],
                "is_commercially_viable": True,
            }

        monkeypatch.setattr(gemini_auditor, "chat_json", fake_chat_json)
        image = tmp_path / "y.jpg"
        _jpeg(image)

        result = gemini_auditor.audit_image(image)
        assert result["flags"] == ["Artificial lighting cast on skin."]
