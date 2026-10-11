"""Tests for the standalone sRGB embed step (raster + transparent PNG).

The defect this guards: a missing sRGB profile is a documented Adobe refusal
reason, and the embed used to live only inside the JPEG upscale path - so PNG
batches and non-upscaled flows never got tagged. The dedicated step must tag
both media types, skip already-tagged files without rewriting them, and move
the working path when it actually writes.
"""

from __future__ import annotations

import io

from PIL import Image

from models import ImageRecord


def _jpeg_bytes(size: tuple[int, int] = (64, 64), color=(200, 60, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _png_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", size, (10, 200, 30, 180)).save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Service level: ensure_srgb_profile
# --------------------------------------------------------------------------- #

class TestEnsureSrgbProfile:
    def test_untagged_jpeg_is_tagged_without_reencode_loss(self, tmp_path):
        from services.srgb_profile import ensure_srgb_profile, has_srgb_profile

        src = tmp_path / "in.jpg"
        src.write_bytes(_jpeg_bytes())

        result = ensure_srgb_profile(src, tmp_path / "out.jpg")
        assert result["ok"] is True
        assert result["applied"] is True
        out = result["output_path"]
        assert out and has_srgb_profile(out)

    def test_already_tagged_file_is_not_rewritten(self, tmp_path):
        from services.srgb_profile import ensure_srgb_profile

        src = tmp_path / "tagged.jpg"
        Image.new("RGB", (64, 64), (1, 2, 3)).save(src, "JPEG", quality=95)
        # Embed once...
        first = ensure_srgb_profile(src, tmp_path / "once.jpg")
        assert first["applied"] is True

        # ...second pass must be a no-op.
        second = ensure_srgb_profile(tmp_path / "once.jpg", tmp_path / "twice.jpg")
        assert second["ok"] is True
        assert second["applied"] is False

    def test_png_keeps_alpha_and_gains_the_profile(self, tmp_path):
        from services.srgb_profile import ensure_srgb_profile, has_srgb_profile

        src = tmp_path / "in.png"
        Image.new("RGBA", (64, 64), (10, 20, 30, 128)).save(src, "PNG")

        result = ensure_srgb_profile(src, tmp_path / "out.png")
        assert result["ok"] is True
        assert result["applied"] is True

        with Image.open(result["output_path"]) as probe:
            assert probe.mode == "RGBA"  # alpha is the PNG's deliverable
            assert probe.getpixel((0, 0))[3] == 128
        assert has_srgb_profile(result["output_path"])

    def test_missing_source_reports_not_ok(self, tmp_path):
        from services.srgb_profile import ensure_srgb_profile

        result = ensure_srgb_profile(tmp_path / "nope.jpg", tmp_path / "out.jpg")
        assert result["ok"] is False
        assert "not found" in result["reason"].lower()


# --------------------------------------------------------------------------- #
# Step level: the runner's _step_embed_srgb
# --------------------------------------------------------------------------- #

def _upload(client, media_type: str, name: str, data: bytes, ext: str):
    response = client.post(
        "/api/batches",
        json={"name": name, "media_type": media_type,
              "steps": [{"key": "embed_srgb"}]},
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    upload = client.post(
        f"/api/batches/{batch['id']}/files",
        files=[("files", (f"asset{ext}", data, "image/png" if ext == ".png" else "image/jpeg"))],
    )
    assert upload.status_code == 200, upload.text
    return batch


class TestEmbedSrgbStep:
    def test_raster_batch_tags_and_moves_working_path(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        from config import settings
        from services import pipeline_runner

        srgb_dir = tmp_path / "srgb"
        monkeypatch.setattr(settings, "SRGB_DIR", srgb_dir)

        batch = _upload(client, "raster", "raster srgb", _jpeg_bytes(), ".jpg")
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        from models import Batch

        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error
        record = session.query(ImageRecord).filter(
            ImageRecord.batch_id == batch["id"]
        ).one()
        detail = (record.stage_details or {}).get("embed_srgb")
        assert detail and detail["ok"] is True and detail["applied"] is True
        assert record.working_path.startswith(str(srgb_dir))
        assert (srgb_dir / f"{record.id}-srgb.jpg").exists()
        session.close()

    def test_png_batch_is_tagged_too(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        """The old upscale-only embed never covered PNG - this step must."""
        from config import settings
        from services import pipeline_runner
        from services.srgb_profile import has_srgb_profile

        srgb_dir = tmp_path / "srgb"
        monkeypatch.setattr(settings, "SRGB_DIR", srgb_dir)

        batch = _upload(client, "png", "png srgb", _png_bytes(), ".png")
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        from models import Batch

        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error
        record = session.query(ImageRecord).filter(
            ImageRecord.batch_id == batch["id"]
        ).one()
        detail = (record.stage_details or {}).get("embed_srgb")
        assert detail and detail["applied"] is True
        assert has_srgb_profile(record.working_path)
        with Image.open(record.working_path) as probe:
            assert probe.mode == "RGBA"  # alpha survived the embed
        session.close()

    def test_rerun_skips_already_tagged_file(
        self, client, db_session_factory, tmp_path, monkeypatch
    ):
        from config import settings
        from services import pipeline_runner

        srgb_dir = tmp_path / "srgb"
        monkeypatch.setattr(settings, "SRGB_DIR", srgb_dir)

        batch = _upload(client, "raster", "rerun srgb", _jpeg_bytes(), ".jpg")
        pipeline_runner.run_batch(db_session_factory, batch["id"])
        pipeline_runner.run_batch(db_session_factory, batch["id"])

        session = db_session_factory()
        from models import Batch

        row = session.get(Batch, batch["id"])
        assert row.status == "completed", row.error
        record = session.query(ImageRecord).filter(
            ImageRecord.batch_id == batch["id"]
        ).one()
        # Second pass: applied=False (already tagged), reported as skipped.
        detail = (record.stage_details or {}).get("embed_srgb")
        assert detail["applied"] is False
        progress = row.step_progress.get("embed_srgb", {})
        assert progress.get("counts", {}).get("skipped") == 1
        session.close()
