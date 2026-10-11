"""Tests for the diversity gate: perceptual clustering + quarantine step.

The defect this guards: Adobe refuses a submission where several images are
variants of the same shot, and the gate is what keeps only the strongest few.
It must (a) cluster genuinely similar images, (b) keep the sharpest, (c)
quarantine the rest recoverably, and (d) never touch terminal records.
"""

from __future__ import annotations

import io

import numpy as np
import pytest
from PIL import Image

from models import Batch, ImageRecord, PipelineStage
from services import diversity_gate


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _pattern_image(seed: int, size: int = 256) -> np.ndarray:
    """Deterministic textured BGR image - Laplacian variance > 0."""
    rng = np.random.default_rng(seed)
    gray = rng.integers(0, 256, size=(size, size), dtype=np.uint8)
    # Blur a copy for the "softer" variant: same composition, less detail.
    return np.stack([gray] * 3, axis=-1)


def _softened(image: np.ndarray) -> np.ndarray:
    """Low-pass the image: identical composition, visibly softer."""
    import cv2

    return cv2.GaussianBlur(image, (9, 9), 4)


def _write(path, image: np.ndarray) -> str:
    import cv2

    assert cv2.imwrite(str(path), image)
    return str(path)


def _png_bytes(seed: int = 1, size: tuple[int, int] = (64, 64)) -> bytes:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(*size[::-1], 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Service level: scoring, clustering, planning
# --------------------------------------------------------------------------- #

class TestGatePlan:
    def test_identical_variants_keep_sharpest(self, tmp_path):
        sharp = _pattern_image(seed=1)
        soft = _softened(sharp)
        entries = [
            ("a", _write(tmp_path / "a.png", sharp)),
            ("b", _write(tmp_path / "b.png", soft)),
        ]
        plan = diversity_gate.gate_batch(entries, threshold=0.85, keep_top=1)

        assert plan["a"]["keep"] is True
        assert plan["b"]["keep"] is False
        assert plan["b"]["kept_over"] == ["a"]
        assert plan["b"]["similarities"].get("a", 0) >= 0.85

    def test_distinct_images_all_kept(self, tmp_path):
        entries = [
            ("a", _write(tmp_path / "a.png", _pattern_image(seed=1))),
            ("b", _write(tmp_path / "b.png", _pattern_image(seed=2))),
            ("c", _write(tmp_path / "c.png", _pattern_image(seed=3))),
        ]
        plan = diversity_gate.gate_batch(entries, threshold=0.85, keep_top=2)
        # Random noise of different seeds shares no dHash structure, so no
        # cluster forms and nothing may be quarantined.
        assert all(decision["keep"] for decision in plan.values())

    def test_keep_top_two_of_three_variants(self, tmp_path):
        base = _pattern_image(seed=5)
        entries = [
            ("v1", _write(tmp_path / "v1.png", base)),
            ("v2", _write(tmp_path / "v2.png", _softened(base))),
            ("v3", _write(tmp_path / "v3.png", _softened(_softened(base)))),
        ]
        plan = diversity_gate.gate_batch(entries, threshold=0.8, keep_top=2)

        kept = sorted(k for k, v in plan.items() if v["keep"])
        dropped = [k for k, v in plan.items() if not v["keep"]]
        assert len(kept) == 2
        assert len(dropped) == 1
        # The double-blurred one is the softest: it must be the one set aside.
        assert dropped == ["v3"]

    def test_unreadable_file_is_kept_not_quarantined(self, tmp_path):
        missing = tmp_path / "gone.png"
        plan = diversity_gate.gate_batch(
            [("gone", missing)], threshold=0.85, keep_top=1
        )
        assert plan["gone"]["keep"] is True
        assert plan["gone"]["readable"] is False

    def test_empty_batch_is_a_noop(self):
        assert diversity_gate.gate_batch([]) == {}


# --------------------------------------------------------------------------- #
# Step level: the runner's _step_diversity_gate
# --------------------------------------------------------------------------- #

def _upload_batch(client, count: int = 3, media_type: str = "png") -> tuple[Batch, list[ImageRecord]]:
    """Create a batch with `count` byte-identical images (worst-case dupes)."""
    response = client.post(
        "/api/batches",
        json={"name": "dupe batch", "media_type": media_type,
              "steps": [{"key": "diversity_gate"}]},
    )
    assert response.status_code == 201, response.text
    batch = response.json()

    files = [
        ("files", (f"variant-{i}.png", _png_bytes(seed=1), "image/png"))
        for i in range(count)
    ]
    upload = client.post(f"/api/batches/{batch['id']}/files", files=files)
    assert upload.status_code == 200, upload.text
    return batch, files


class TestDiversityGateStep:
    @pytest.fixture()
    def quarantine(self, tmp_path, monkeypatch):
        from config import settings

        path = tmp_path / "quarantine"
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(settings, "QUARANTINE_DIR", path)
        return path

    def test_similar_variants_are_quarantined_and_recoverable(
        self, client, db_session_factory, quarantine
    ):
        from services import pipeline_runner

        batch, _ = _upload_batch(client, count=3)
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error

        records = (
            session.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch["id"])
            .all()
        )
        quarantined = [r for r in records if r.stage == PipelineStage.QUARANTINED]
        kept = [r for r in records if r.stage != PipelineStage.QUARANTINED]

        # keep_top default is 2: two survive, one is set aside.
        assert len(kept) == 2
        assert len(quarantined) == 1
        session.close()

        # Recoverable: the file physically lives in storage/quarantine.
        moved = quarantined[0]
        assert moved.working_path
        survivors = list(quarantine.glob(f"{moved.id}-*"))
        assert survivors, f"quarantine is empty: {list(quarantine.glob('*'))}"

    def test_quarantined_records_are_terminal_and_metadata_blocked(
        self, client, db_session_factory, quarantine
    ):
        from services import pipeline_runner
        from services.stage_registry import TERMINAL_STAGES
        from tasks.stage_orchestrator import METADATA_BLOCKED_STAGES

        batch, _ = _upload_batch(client, count=2)
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        records = (
            session.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch["id"])
            .all()
        )
        for record in records:
            if record.stage == PipelineStage.QUARANTINED:
                assert record.stage in TERMINAL_STAGES
                assert record.stage in METADATA_BLOCKED_STAGES
                detail = (record.stage_details or {}).get("diversity_gate")
                assert detail and detail["keep"] is False
                assert detail["action"] == "quarantine"
        session.close()

    def test_rerun_skips_already_gated_records(
        self, client, db_session_factory, quarantine
    ):
        from services import pipeline_runner

        batch, _ = _upload_batch(client, count=3)
        pipeline_runner.run_batch(db_session_factory, batch["id"])
        # Re-running must not move a quarantined file twice or flip a keeper.
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error
        records = (
            session.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch["id"])
            .all()
        )
        assert sum(1 for r in records if r.stage == PipelineStage.QUARANTINED) == 1
        session.close()
        # Exactly one file in quarantine after two runs.
        assert len(list(quarantine.glob("*"))) == 1

    def test_reject_action_leaves_file_in_place(
        self, client, db_session_factory, quarantine, monkeypatch
    ):
        from services import pipeline_runner

        batch, _ = _upload_batch(client, count=3)
        # Patch the step's default action through the stored step config.
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.steps = [{"key": "diversity_gate", "config": {"action": "reject"}}]
        session.commit()
        session.close()

        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        records = (
            session.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch["id"])
            .all()
        )
        quarantined = [r for r in records if r.stage == PipelineStage.QUARANTINED]
        assert len(quarantined) == 1
        # Reject = stay where they are: quarantine dir untouched.
        assert len(list(quarantine.glob("*"))) == 0
        session.close()
