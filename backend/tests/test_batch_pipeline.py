"""Tests for batch pipeline v2: catalog, batches, step profiles, runner.

Fixture conventions follow ``conftest.py``: ``client`` (dependency-overridden
TestClient) plus ``db_session_factory`` for direct DB access. The runner is
always driven with the *test* factory — ``database.SessionLocal`` points at the
real development database, and writing there from a test is how cross-test
pollution happens.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from models import Batch, ImageRecord


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _png_bytes(size: tuple[int, int] = (64, 64), color=(200, 40, 40, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def _jpg_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (30, 120, 200)).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _create_batch(client, media_type="raster", steps=None, name="Test batch", **extra):
    payload = {"name": name, "media_type": media_type, **extra}
    if steps is not None:
        payload["steps"] = steps
    response = client.post("/api/batches", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- #
# Step catalog
# --------------------------------------------------------------------------- #

class TestStepCatalog:
    def test_catalog_lists_all_steps_in_canonical_order(self, client):
        data = client.get("/api/batches/steps").json()
        # Upscale leads so masking happens on the high-res pixels, never on a
        # copy whose alpha has already been resampled.
        assert data["order"] == [
            "upscale", "bg_remove", "ocr", "refine", "compatibility",
            "pure_white", "diversity_gate", "embed_srgb", "metadata",
        ]
        keys = [s["key"] for s in data["steps"]]
        assert keys == data["order"]

    def test_raster_catalog_excludes_bg_remove(self, client):
        data = client.get("/api/batches/steps", params={"media_type": "raster"}).json()
        keys = {s["key"] for s in data["steps"]}
        assert "bg_remove" not in keys
        assert keys == {
            "ocr", "upscale", "refine", "compatibility", "pure_white",
            "diversity_gate", "embed_srgb", "metadata",
        }

    def test_pure_white_is_raster_only(self, client):
        png = client.get("/api/batches/steps", params={"media_type": "png"}).json()
        assert "pure_white" not in {s["key"] for s in png["steps"]}

        raster = client.get(
            "/api/batches/steps", params={"media_type": "raster"}
        ).json()
        step = next(s for s in raster["steps"] if s["key"] == "pure_white")
        config = step["default_config"]
        assert config["threshold"] == 245
        assert config["border_min"] == 248
        assert config["protect_subject"] is True

    def test_png_catalog_excludes_refine_and_compatibility(self, client):
        data = client.get("/api/batches/steps", params={"media_type": "png"}).json()
        keys = {s["key"] for s in data["steps"]}
        assert keys == {
            "upscale", "bg_remove", "ocr", "diversity_gate", "embed_srgb", "metadata"
        }

    def test_invalid_media_type_is_400(self, client):
        response = client.get("/api/batches/steps", params={"media_type": "gif"})
        assert response.status_code == 400

    def test_every_step_carries_defaults_and_a_label(self, client):
        for step in client.get("/api/batches/steps").json()["steps"]:
            assert step["label"]
            assert step["description"]
            assert isinstance(step["default_config"], dict)

    def test_media_types_block_lists_match_the_order(self, client):
        data = client.get("/api/batches/steps").json()
        assert data["media_types"]["raster"] == [
            "upscale", "ocr", "refine", "compatibility", "pure_white",
            "diversity_gate", "embed_srgb", "metadata",
        ]
        assert data["media_types"]["png"] == [
            "upscale", "bg_remove", "ocr", "diversity_gate", "embed_srgb", "metadata"
        ]

    def test_bg_remove_defaults_expose_the_stock_grade_pipeline(self, client):
        steps = client.get(
            "/api/batches/steps", params={"media_type": "png"}
        ).json()["steps"]
        config = next(s for s in steps if s["key"] == "bg_remove")["default_config"]
        # GPU segmentation + SOTA model + the three post-mask stages + audit.
        assert config["gpu"] is True
        assert config["model"].startswith("birefnet")
        assert {"matting", "defringe", "sanitize", "edge_check"} <= set(config)


# --------------------------------------------------------------------------- #
# Batch CRUD
# --------------------------------------------------------------------------- #

class TestBatchCrud:
    def test_create_with_no_steps_is_400(self, client):
        response = client.post(
            "/api/batches", json={"media_type": "raster", "steps": []}
        )
        assert response.status_code == 400

    def test_create_normalises_and_defaults(self, client):
        batch = _create_batch(
            client,
            steps=[
                {"key": "ocr"},
                {"key": "upscale", "config": {"target_long_edge": 2560}},
                {"key": "nonsense"},  # dropped silently
            ],
        )
        keys = [s["key"] for s in batch["steps"]]
        # The requested order is preserved (junk still removed): the operator
        # arranges the pipeline, the server does not re-sort it.
        assert keys == ["ocr", "upscale"]
        upscale = next(s for s in batch["steps"] if s["key"] == "upscale")
        assert upscale["config"]["target_long_edge"] == 2560
        assert "gpu_id" in upscale["config"]  # defaults merged in

    def test_a_custom_order_survives_create_and_patch(self, client):
        created = _create_batch(
            client,
            steps=[{"key": "metadata"}, {"key": "ocr"}, {"key": "upscale"}],
        )
        assert [s["key"] for s in created["steps"]] == ["metadata", "ocr", "upscale"]

        patched = client.patch(
            f"/api/batches/{created['id']}",
            json={"steps": [{"key": "upscale"}, {"key": "metadata"}]},
        )
        assert patched.status_code == 200
        assert [s["key"] for s in patched.json()["steps"]] == ["upscale", "metadata"]

    def test_png_batch_rejects_refine(self, client):
        batch = _create_batch(
            client, media_type="png", steps=[{"key": "bg_remove"}, {"key": "refine"}]
        )
        keys = [s["key"] for s in batch["steps"]]
        assert keys == ["bg_remove"]  # refine not pickable for png -> dropped

    def test_batch_with_no_valid_steps_is_400(self, client):
        response = client.post(
            "/api/batches",
            json={"media_type": "png", "steps": [{"key": "refine"}]},
        )
        assert response.status_code == 400

    def test_invalid_media_type_is_400(self, client):
        response = client.post(
            "/api/batches", json={"media_type": "tiff", "steps": [{"key": "ocr"}]}
        )
        assert response.status_code == 400

    def test_get_batch_returns_steps_and_counts(self, client):
        created = _create_batch(client, steps=[{"key": "ocr"}])
        fetched = client.get(f"/api/batches/{created['id']}").json()
        assert fetched["id"] == created["id"]
        assert fetched["status"] == "draft"
        assert fetched["record_count"] == 0
        assert fetched["records"] == []

    def test_list_batches_newest_first(self, client):
        first = _create_batch(client, name="First", steps=[{"key": "ocr"}])
        second = _create_batch(client, name="Second", steps=[{"key": "ocr"}])
        items = client.get("/api/batches").json()["items"]
        ids = [b["id"] for b in items]
        assert ids.index(second["id"]) < ids.index(first["id"])

    def test_patch_rewrites_steps_and_resets_status(self, client, db_session_factory):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.status = "completed"
        session.commit()
        session.close()

        response = client.patch(
            f"/api/batches/{batch['id']}",
            json={"steps": [{"key": "ocr"}, {"key": "metadata"}]},
        )
        assert response.status_code == 200
        updated = response.json()
        assert [s["key"] for s in updated["steps"]] == ["ocr", "metadata"]
        assert updated["status"] == "draft"  # editing re-opens the batch

    def test_delete_batch_removes_it(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.delete(f"/api/batches/{batch['id']}")
        assert response.status_code == 200
        assert client.get(f"/api/batches/{batch['id']}").status_code == 404

    def test_delete_completed_batch_cascades_records_and_files(
        self, client, db_session_factory, tmp_path
    ):
        """Deleting a processed batch wipes rows *and* on-disk artifacts."""
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(
            f"/api/batches/{batch['id']}/files",
            files=[
                ("files", ("a.jpg", _jpg_bytes(), "image/jpeg")),
                ("files", ("b.jpg", _jpg_bytes(), "image/jpeg")),
            ],
        )
        assert response.status_code == 200, response.text
        record_ids = response.json()["record_ids"]
        assert len(record_ids) == 2

        session = db_session_factory()
        paths: list[str] = []
        for record_id in record_ids:
            record = session.get(ImageRecord, record_id)
            paths.extend(
                p
                for p in (
                    record.original_path,
                    record.thumbnail_path,
                    record.working_path,
                )
                if p
            )
        session.get(Batch, batch["id"]).status = "completed"
        session.commit()
        session.close()

        # Sanity: the files really are on disk before the delete.
        assert any(Path(p).is_file() for p in paths)
        assert any((tmp_path / "inbox").iterdir())
        assert any((tmp_path / "thumbnails").iterdir())

        response = client.delete(f"/api/batches/{batch['id']}")
        assert response.status_code == 200, response.text
        assert response.json() == {"deleted": batch["id"], "images": 2}

        assert client.get(f"/api/batches/{batch['id']}").status_code == 404

        session = db_session_factory()
        for record_id in record_ids:
            assert session.get(ImageRecord, record_id) is None
        assert (
            session.query(ImageRecord)
            .filter(ImageRecord.batch_id == batch["id"])
            .count()
            == 0
        )
        session.close()

        for path in paths:
            assert not Path(path).exists(), path
        assert not any((tmp_path / "inbox").iterdir())
        assert not any((tmp_path / "thumbnails").iterdir())

    def test_unknown_batch_is_404(self, client):
        assert client.get("/api/batches/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #

class TestBatchUpload:
    def test_raster_upload_converts_png_to_jpeg(self, client, db_session_factory):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(
            f"/api/batches/{batch['id']}/files",
            files=[("files", ("photo.png", _png_bytes(), "image/png"))],
        )
        assert response.status_code == 200, response.text
        record_id = response.json()["record_ids"][0]

        session = db_session_factory()
        record = session.get(ImageRecord, record_id)
        assert record.batch_id == batch["id"]
        assert record.working_path.endswith(".jpg")  # converted
        assert record.original_path.endswith(".png")  # original kept
        session.close()

    def test_png_batch_keeps_alpha_png(self, client, db_session_factory):
        batch = _create_batch(client, media_type="png", steps=[{"key": "bg_remove"}])
        response = client.post(
            f"/api/batches/{batch['id']}/files",
            files=[("files", ("object.png", _png_bytes(), "image/png"))],
        )
        assert response.status_code == 200, response.text
        session = db_session_factory()
        record = session.get(ImageRecord, response.json()["record_ids"][0])
        assert record.working_path == record.original_path  # no conversion
        assert record.working_path.endswith(".png")
        session.close()

    def test_bad_extension_is_400(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(
            f"/api/batches/{batch['id']}/files",
            files=[("files", ("evil.gif", b"GIF89a", "image/gif"))],
        )
        assert response.status_code == 400

    def test_upload_updates_record_count(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        client.post(
            f"/api/batches/{batch['id']}/files",
            files=[
                ("files", ("a.jpg", _jpg_bytes(), "image/jpeg")),
                ("files", ("b.jpg", _jpg_bytes(), "image/jpeg")),
            ],
        )
        fetched = client.get(f"/api/batches/{batch['id']}").json()
        assert fetched["record_count"] == 2


# --------------------------------------------------------------------------- #
# Run / cancel preconditions
# --------------------------------------------------------------------------- #

class TestRunPreconditions:
    def test_run_without_images_is_409(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(f"/api/batches/{batch['id']}/run")
        assert response.status_code == 409
        assert "image" in response.json()["detail"].lower()

    def test_queue_without_images_is_409(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        response = client.post(f"/api/batches/{batch['id']}/queue")
        assert response.status_code == 409
        assert "image" in response.json()["detail"].lower()

    def test_queue_on_running_is_409(self, client, db_session_factory):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.status = "running"
        session.commit()
        session.close()

        response = client.post(f"/api/batches/{batch['id']}/queue")
        assert response.status_code == 409
        assert "already running" in response.json()["detail"]

    def test_queue_on_queued_is_409_for_both_run_paths(
        self, client, db_session_factory
    ):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.status = "queued"
        session.commit()
        session.close()

        assert client.post(
            f"/api/batches/{batch['id']}/queue"
        ).status_code == 409
        assert client.post(
            f"/api/batches/{batch['id']}/run"
        ).status_code == 409

    def test_cancel_on_draft_is_409(self, client):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        assert client.post(f"/api/batches/{batch['id']}/cancel").status_code == 409

    def test_running_batch_cannot_be_edited_or_deleted(
        self, client, db_session_factory
    ):
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.status = "running"
        session.commit()
        session.close()

        assert client.patch(
            f"/api/batches/{batch['id']}", json={"name": "x"}
        ).status_code == 409
        delete = client.delete(f"/api/batches/{batch['id']}")
        assert delete.status_code == 409
        assert "cancel" in delete.json()["detail"].lower()
        assert client.post(f"/api/batches/{batch['id']}/run").status_code == 409

    def test_queued_batch_cannot_be_deleted(
        self, client, db_session_factory
    ):
        """A queued batch could be claimed mid-delete — cancel first."""
        batch = _create_batch(client, steps=[{"key": "ocr"}])
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        row.status = "queued"
        session.commit()
        session.close()

        response = client.delete(f"/api/batches/{batch['id']}")
        assert response.status_code == 409
        assert "cancel" in response.json()["detail"].lower()
        # The guard refused before touching anything.
        assert client.get(f"/api/batches/{batch['id']}").status_code == 200


# --------------------------------------------------------------------------- #
# Step profiles
# --------------------------------------------------------------------------- #

class TestStepProfiles:
    def test_create_list_delete_roundtrip(self, client):
        created = client.post(
            "/api/step-profiles",
            json={
                "name": "My raster recipe",
                "media_type": "raster",
                "steps": [{"key": "ocr"}, {"key": "upscale"}],
            },
        )
        assert created.status_code == 201, created.text
        profile = created.json()
        # Profiles keep the order they were saved in, too.
        assert [s["key"] for s in profile["steps"]] == ["ocr", "upscale"]

        listing = client.get(
            "/api/step-profiles", params={"media_type": "raster"}
        ).json()
        assert any(p["id"] == profile["id"] for p in listing["items"])

        assert client.delete(f"/api/step-profiles/{profile['id']}").status_code == 200
        after = client.get("/api/step-profiles").json()["items"]
        assert all(p["id"] != profile["id"] for p in after)

    def test_profile_requires_name(self, client):
        response = client.post(
            "/api/step-profiles", json={"name": "  ", "steps": [{"key": "ocr"}]}
        )
        assert response.status_code == 400

    def test_profile_steps_are_validated(self, client):
        response = client.post(
            "/api/step-profiles",
            json={"name": "bad", "media_type": "png", "steps": [{"key": "refine"}]},
        )
        assert response.status_code == 400

    def test_batch_seeds_from_profile(self, client):
        profile = client.post(
            "/api/step-profiles",
            json={
                "name": "Cut-out recipe",
                "media_type": "png",
                "steps": [
                    {"key": "bg_remove", "config": {"model": "u2net"}},
                    {"key": "metadata"},
                ],
            },
        ).json()

        batch = _create_batch(
            client, media_type="png", steps=[], profile_id=profile["id"]
        )
        assert batch["profile_id"] == profile["id"]
        assert [s["key"] for s in batch["steps"]] == ["bg_remove", "metadata"]
        bg = next(s for s in batch["steps"] if s["key"] == "bg_remove")
        assert bg["config"]["model"] == "u2net"

    def test_profile_media_type_mismatch_is_400(self, client):
        profile = client.post(
            "/api/step-profiles",
            json={"name": "Raster", "media_type": "raster", "steps": [{"key": "ocr"}]},
        ).json()
        response = client.post(
            "/api/batches",
            json={"media_type": "png", "steps": [], "profile_id": profile["id"]},
        )
        assert response.status_code == 400


# --------------------------------------------------------------------------- #
# Pipeline runner (unit level, stubbed steps)
# --------------------------------------------------------------------------- #

def _make_batch_with_image(client, steps, media_type="raster"):
    batch = _create_batch(client, media_type=media_type, steps=steps)
    client.post(
        f"/api/batches/{batch['id']}/files",
        files=[("files", ("a.jpg", _jpg_bytes(), "image/jpeg"))],
    )
    return batch


class TestPipelineRunner:
    def test_runner_marks_batch_failed_without_images(
        self, client, db_session_factory
    ):
        from services import pipeline_runner

        batch = _create_batch(client, steps=[{"key": "ocr"}])
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "failed"
        assert "no images" in (row.error or "").lower()
        session.close()

    def test_runner_executes_steps_in_the_stored_order(
        self, client, db_session_factory, monkeypatch
    ):
        from services import pipeline_runner

        # Deliberately NOT the catalog's canonical order: the runner must walk
        # the list the operator saved, not re-sort it.
        batch = _make_batch_with_image(
            client, [{"key": "metadata"}, {"key": "ocr"}]
        )

        calls: list[str] = []

        def fake_run(key, db_f, record_ids, config, job, cfg):
            calls.append(key)
            from services.jobs import STATUS_COMPLETED, registry

            registry.finish(job, STATUS_COMPLETED)
            return {"status": "completed", "message": "ok", "counts": {"succeeded": 1}}

        monkeypatch.setattr(pipeline_runner, "_run_stage_step", fake_run)
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        assert calls == ["metadata", "ocr"]
        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "completed"
        assert row.step_progress["metadata"]["status"] == "completed"
        session.close()

    def test_runner_stops_on_step_failure(
        self, client, db_session_factory, monkeypatch
    ):
        from services import pipeline_runner

        batch = _make_batch_with_image(client, [{"key": "ocr"}, {"key": "metadata"}])

        def failing_run(key, db_f, record_ids, config, job, cfg):
            from services.jobs import STATUS_FAILED, registry

            registry.finish(job, STATUS_FAILED)
            return {"status": "failed", "message": "boom", "counts": {"failed": 1}}

        monkeypatch.setattr(pipeline_runner, "_run_stage_step", failing_run)
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "failed"
        assert "ocr" in (row.error or "")
        # The second step never ran.
        assert row.step_progress["metadata"]["status"] == "pending"
        session.close()

    def test_runner_resolves_png_upscale_to_the_alpha_path(
        self, client, db_session_factory, monkeypatch
    ):
        from services import pipeline_runner

        batch = _make_batch_with_image(client, [{"key": "upscale"}], media_type="png")

        seen: list[str] = []

        def fake_png_upscale(db_f, records, config, job, cfg):
            seen.append("png")
            from services.jobs import STATUS_COMPLETED, registry

            registry.finish(job, STATUS_COMPLETED)
            return {"status": "completed", "message": "", "counts": {"succeeded": 1}}

        monkeypatch.setattr(pipeline_runner, "_step_upscale_png", fake_png_upscale)
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        assert seen == ["png"]
        session = db_session_factory()
        assert session.get(Batch, batch["id"]).status == "completed"
        session.close()

    def test_bg_remove_passes_its_config_and_records_the_dual_matte_audit(
        self, client, db_session_factory, monkeypatch, tmp_path
    ):
        """The step config must reach the model, and the QC must be the audit.

        A stubbed remover proves the *plumbing* (config in, ``dual_matte`` out)
        without needing ONNX weights in CI; the matting maths itself is covered
        by ``tests/test_matting.py``.
        """
        from services import bg_remover, pipeline_runner
        from services.bg_remover import RemoveResult

        batch = _create_batch(
            client,
            media_type="png",
            steps=[{"key": "bg_remove", "config": {"model": "u2net", "matting": "off"}}],
        )
        client.post(
            f"/api/batches/{batch['id']}/files",
            files=[("files", ("a.png", _png_bytes(), "image/png"))],
        )

        seen: dict = {}

        def fake_remove(source, record_id, *, model, cfg, options):
            seen["model"] = model
            seen["options"] = options
            out = tmp_path / f"{record_id}.png"
            rgba = np.zeros((64, 64, 4), np.uint8)
            rgba[16:48, 16:48] = (40, 90, 160, 255)
            rgba[24:40, 24:40, 3] = 200  # soft band, so the audit has an edge
            Image.fromarray(rgba, "RGBA").save(out)
            return RemoveResult(
                success=True, output_path=str(out), model=model, width=64, height=64
            )

        monkeypatch.setattr(bg_remover, "remove_background", fake_remove)
        released: list[bool] = []
        monkeypatch.setattr(
            bg_remover, "release_sessions", lambda: released.append(True) or 0
        )
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        # The ~1 GB ONNX session must not outlive the step that used it.
        assert released, "the runner must hand the model back when the step ends"

        assert seen["model"] == "u2net"
        assert seen["options"]["gpu"] is True  # default merged in
        assert seen["options"]["matting"] == "off"
        assert seen["options"]["edge_check"] is True  # default merged in

        session = db_session_factory()
        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error
        record = session.query(ImageRecord).filter_by(batch_id=batch["id"]).one()
        detail = record.stage_details["bg_remove"]
        assert detail["model"] == "u2net"
        audit = detail["edge_quality"]
        assert {"coverage", "fringe_px", "jaggedness", "halo", "verdict"} <= set(audit)
        assert {"contour_jaggedness", "halo_black", "halo_white", "exposed_on"} <= set(
            audit["dual_matte"]
        )
        assert audit["verdict"] in {"pass", "warn", "fail"}
        session.close()

    def test_recover_interrupted_batches(self):
        from sqlalchemy import create_engine, text

        from services.pipeline_runner import recover_interrupted_batches

        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TABLE batches (id TEXT PRIMARY KEY, status TEXT, error TEXT)"
            ))
            conn.execute(text(
                "INSERT INTO batches (id, status) VALUES ('stuck', 'running')"
            ))
        assert recover_interrupted_batches(engine) == 1
        with engine.connect() as conn:
            status = conn.execute(
                text("SELECT status FROM batches WHERE id = 'stuck'")
            ).scalar()
        assert status == "failed"
        engine.dispose()


# --------------------------------------------------------------------------- #
# Edge quality (synthetic ground truth)
# --------------------------------------------------------------------------- #

def _write_rgba(tmp_path, kind: str):
    size = 64
    yy, xx = np.mgrid[0:size, 0:size]
    dist = np.sqrt((xx - 32) ** 2 + (yy - 32) ** 2)
    if kind == "smooth":
        alpha = np.clip((24 - dist) * 80, 0, 255)  # clean AA'd disc
    elif kind == "checker":
        alpha = np.where(dist < 24, 255, 0).astype(float)
        alpha[20:28, :] = np.where(np.arange(size) % 2 == 0, 255, 0)
    else:  # empty
        alpha = np.zeros((size, size))
    pixels = np.zeros((size, size, 4), dtype="uint8")
    pixels[:, :, 0] = 255
    pixels[:, :, 3] = alpha.astype("uint8")
    path = tmp_path / f"{kind}.png"
    Image.fromarray(pixels, "RGBA").save(path)
    return path


class TestEdgeQuality:
    def test_clean_cutout_passes(self, tmp_path):
        from services.edge_quality import check_edges

        report = check_edges(_write_rgba(tmp_path, "smooth"))
        assert report.verdict in ("pass", "warn")
        assert 0.0 < report.coverage < 1.0
        assert report.issues  # always explains itself

    def test_empty_cutout_fails(self, tmp_path):
        from services.edge_quality import check_edges

        report = check_edges(_write_rgba(tmp_path, "empty"))
        assert report.verdict == "fail"
        assert any("empty" in issue.lower() for issue in report.issues)

    def test_unreadable_file_fails_gracefully(self, tmp_path):
        from services.edge_quality import check_edges

        bogus = tmp_path / "bogus.png"
        bogus.write_bytes(b"not a png")
        report = check_edges(bogus)
        assert report.verdict == "fail"
        assert report.issues
