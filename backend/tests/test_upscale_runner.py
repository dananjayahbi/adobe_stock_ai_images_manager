"""Unit tests for the Upscayl CLI driver and job progress accounting.

The CLI is never invoked here. Its real behaviour was probed by hand and encoded
in these tests: the exit code is 1 *even on success*, verbose progress is printed
as bare percentages on stdout, and the Vulkan device list is echoed at startup.
Those quirks are what the driver exists to absorb, so they are asserted directly.
"""

import io

import pytest

from services import jobs as job_registry
from services.upscale import options as upscale_options
from services.upscale import runner


@pytest.fixture()
def settings():
    from config import settings as cfg

    return cfg


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #


def test_build_command_emits_every_configured_flag(tmp_path, settings):
    resolved = upscale_options.from_payload(
        {
            "model": "4xNomos8kSC",
            "model_scale": 4,
            "gpu_id": 0,
            "compression": 90,
            "tile_size": 256,
            "tta": True,
        },
        settings,
    )

    command = runner._build_command(
        "upscayl-bin.exe", tmp_path / "in.jpg", tmp_path / "out.png", resolved, tmp_path
    )

    assert command[0] == "upscayl-bin.exe"
    assert "-i" in command and "-o" in command
    assert command[command.index("-n") + 1] == "4xNomos8kSC"
    assert command[command.index("-z") + 1] == "4"
    assert command[command.index("-g") + 1] == "0"
    assert command[command.index("-j") + 1] == "1:2:2"
    assert command[command.index("-t") + 1] == "256"
    assert "-x" in command  # TTA


def test_build_command_always_renders_a_lossless_png(tmp_path, settings):
    resolved = upscale_options.default_options(settings)

    command = runner._build_command(
        "upscayl-bin.exe", tmp_path / "in.jpg", tmp_path / "out.png", resolved, tmp_path
    )

    # The intermediate must be PNG: encoding to JPEG here would discard detail
    # before our own sRGB-tagged final encode.
    assert command[command.index("-f") + 1] == "png"
    # Verbose is mandatory - it is the only source of progress.
    assert "-v" in command


def test_build_command_omits_tile_when_auto(tmp_path, settings):
    resolved = upscale_options.from_payload({"tile_size": 0}, settings)

    command = runner._build_command(
        "upscayl-bin.exe", tmp_path / "in.jpg", tmp_path / "out.png", resolved, tmp_path
    )

    # 0 means "let ncnn decide", which is the CLI default; passing it is noise.
    assert "-t" not in command


def test_build_command_omits_tta_by_default(tmp_path, settings):
    resolved = upscale_options.default_options(settings)

    command = runner._build_command(
        "upscayl-bin.exe", tmp_path / "in.jpg", tmp_path / "out.png", resolved, tmp_path
    )

    assert "-x" not in command


# --------------------------------------------------------------------------- #
# Progress parsing
# --------------------------------------------------------------------------- #


class FakeProcess:
    """Stands in for ``subprocess.Popen`` with scripted stdout lines."""

    def __init__(self, lines, returncode=1):
        self.stdout = io.StringIO("\n".join(lines) + "\n")
        self.returncode = returncode
        self.killed = False

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        self.killed = True


def test_run_pass_reports_progress(monkeypatch):
    lines = ["[0 NVIDIA GeForce GTX 1660 Ti] queueC=2[8]", "0.00%", "50.00%", "100.00%"]
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: FakeProcess(lines))

    seen: list[tuple[float, str]] = []
    completed, _ = runner._run_pass(
        ["upscayl-bin.exe"],
        timeout=60,
        on_progress=lambda pct, label: seen.append((pct, label)),
        pass_index=0,
        pass_count=1,
    )

    assert completed is True
    assert [round(pct) for pct, _ in seen] == [0, 50, 100]
    assert "pass 1/1" in seen[-1][1]


def test_run_pass_ignores_the_vulkan_device_banner(monkeypatch):
    # The banner carries no '%', so it must not be mistaken for progress.
    monkeypatch.setattr(
        runner.subprocess, "Popen", lambda *a, **k: FakeProcess(["[0 NVIDIA GeForce GTX 1660 Ti]"])
    )

    seen: list[float] = []
    runner._run_pass(
        ["upscayl-bin.exe"],
        timeout=60,
        on_progress=lambda pct, label: seen.append(pct),
        pass_index=0,
        pass_count=1,
    )

    assert seen == []


def test_run_pass_spreads_progress_across_passes(monkeypatch):
    monkeypatch.setattr(
        runner.subprocess, "Popen", lambda *a, **k: FakeProcess(["50.00%", "100.00%"])
    )

    seen: list[float] = []
    runner._run_pass(
        ["upscayl-bin.exe"],
        timeout=60,
        on_progress=lambda pct, label: seen.append(pct),
        pass_index=1,
        pass_count=2,
    )

    # The second pass owns the 50-100% band of the overall run.
    assert seen[0] == pytest.approx(75.0)
    assert seen[1] == pytest.approx(100.0)


def test_run_pass_succeeds_despite_a_nonzero_exit_code(monkeypatch):
    monkeypatch.setattr(
        runner.subprocess, "Popen", lambda *a, **k: FakeProcess(["100.00%"], returncode=1)
    )

    completed, diagnostics = runner._run_pass(
        ["upscayl-bin.exe"], timeout=60, on_progress=None, pass_index=0, pass_count=1
    )

    # Probed reality: the binary prints "Upscayled Successfully!" and exits 1.
    assert completed is True
    assert diagnostics == ""


def test_run_pass_collects_error_lines_without_failing(monkeypatch):
    lines = ["could not load model", "100.00%"]
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: FakeProcess(lines))

    completed, diagnostics = runner._run_pass(
        ["upscayl-bin.exe"], timeout=60, on_progress=None, pass_index=0, pass_count=1
    )

    # Diagnostics are kept for the failure path; a warning alone is not failure.
    assert completed is True
    assert "could not load model" in diagnostics


def test_run_pass_reports_a_missing_binary(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(runner.subprocess, "Popen", boom)

    completed, diagnostics = runner._run_pass(
        ["missing.exe"], timeout=60, on_progress=None, pass_index=0, pass_count=1
    )

    assert completed is False
    assert "Could not run the upscaler" in diagnostics


def test_run_pass_ignores_non_monotonic_percentages(monkeypatch):
    # ncnn emits per-tile percentages, so values repeat and can dip mid-run.
    monkeypatch.setattr(
        runner.subprocess,
        "Popen",
        lambda *a, **k: FakeProcess(["50.00%", "50.00%", "25.00%", "100.00%"]),
    )

    seen: list[float] = []
    runner._run_pass(
        ["upscayl-bin.exe"],
        timeout=60,
        on_progress=lambda pct, label: seen.append(pct),
        pass_index=0,
        pass_count=1,
    )

    # Repeats and regressions are dropped, so the UI bar never runs backwards.
    assert seen == [50.0, 100.0]


# --------------------------------------------------------------------------- #
# Geometry helpers
# --------------------------------------------------------------------------- #


def test_target_dimensions_preserve_aspect_ratio():
    assert runner._target_dimensions(896, 1200, 3840) == (2867, 3840)


def test_target_dimensions_handle_a_degenerate_source():
    assert runner._target_dimensions(0, 0, 3840) == (0, 0)


def test_resize_to_uses_area_when_shrinking():
    import numpy as np

    image = np.zeros((100, 200, 3), dtype=np.uint8)
    resized = runner._resize_to(image, 100, 50)

    assert resized.shape[:2] == (50, 100)


def test_resize_to_is_a_no_op_when_already_correct():
    import numpy as np

    image = np.zeros((50, 100, 3), dtype=np.uint8)
    assert runner._resize_to(image, 100, 50) is image


# --------------------------------------------------------------------------- #
# Job progress accounting
# --------------------------------------------------------------------------- #


def make_job(record_ids: list[str]) -> job_registry.Job:
    """Register a batch the way the router does, without touching the database."""
    items = [job_registry.JobItem(record_id=rid, filename=f"{rid}.jpg") for rid in record_ids]
    return job_registry.JobRegistry().create("upscale", "upscale", items)


def test_job_item_serialises_progress_and_detail():
    item = job_registry.JobItem(record_id="abc", filename="a.jpg")
    item.progress = 37.5
    item.detail = "Upscaling · pass 1/2 · 40%"

    payload = item.to_dict()

    assert payload["progress"] == 37.5
    assert payload["detail"] == "Upscaling · pass 1/2 · 40%"


def test_job_item_progress_is_null_when_unknown():
    item = job_registry.JobItem(record_id="abc", filename="a.jpg")

    # None (not 0) tells the UI to show an indeterminate bar rather than a bar
    # stuck at zero for the whole run.
    assert item.to_dict()["progress"] is None


def test_report_progress_updates_the_running_item():
    job = make_job(["a", "b"])

    job.report_progress("a", 50.0, "Upscaling · pass 1/2 · 50%")

    item = next(i for i in job.items if i.record_id == "a")
    assert item.progress == 50.0
    assert item.detail == "Upscaling · pass 1/2 · 50%"


def test_report_progress_keeps_the_previous_label_when_none_is_given():
    job = make_job(["a"])
    job.report_progress("a", 10.0, "Upscaling · pass 1/2 · 10%")

    job.report_progress("a", 20.0)

    item = job.items[0]
    assert item.progress == 20.0
    assert item.detail == "Upscaling · pass 1/2 · 10%"


def test_report_progress_ignores_unknown_records():
    job = make_job(["a"])

    # A stale callback after a cancel must not resurrect a record.
    job.report_progress("ghost", 50.0)

    assert all(i.record_id != "ghost" for i in job.items)


def test_report_progress_clamps_out_of_range_values():
    job = make_job(["a"])

    job.report_progress("a", 240.0)
    assert job.items[0].progress == 100.0

    job.report_progress("a", -5.0)
    assert job.items[0].progress == 0.0


def test_job_progress_weights_the_running_item():
    job = make_job(["a", "b", "c", "d"])
    job.items[0].status = "running"

    job.report_progress("a", 50.0)

    # One of four records is half done: 0.5/4 = 0.125. Without the weighting the
    # bar would sit at 0 for the entire first image.
    assert job.progress == pytest.approx(0.125)
    assert job.to_dict()["current_record_id"] == "a"


def test_job_progress_reaches_one_when_everything_finishes():
    job = make_job(["a", "b"])
    for item in job.items:
        item.status = "succeeded"

    assert job.progress == pytest.approx(1.0)
    assert job.to_dict()["current_record_id"] is None


def test_job_progress_never_exceeds_one():
    job = make_job(["a", "b"])
    job.items[0].status = "running"
    job.report_progress("a", 100.0)

    assert job.progress <= 1.0


def test_job_serialises_the_new_progress_fields():
    job = make_job(["a"])
    job.items[0].status = "running"
    job.progress_label = "Upscaling to 4K · model 4xNomos8kSC (4x) · GPU 0"
    job.report_progress("a", 10.0, "Upscaling · pass 1/1 · 10%")

    payload = job.to_dict()

    assert payload["current_record_id"] == "a"
    assert payload["progress_label"].startswith("Upscaling to 4K")
    assert payload["items"][0]["detail"] == "Upscaling · pass 1/1 · 10%"
    assert payload["items"][0]["progress"] == 10.0


def test_job_item_reports_a_duration_once_finished():
    item = job_registry.JobItem(record_id="a", filename="a.jpg")
    item.started_at = 100.0
    item.finished_at = 108.25

    assert item.to_dict()["duration_seconds"] == 8.25


# --------------------------------------------------------------------------- #
# Stage label
# --------------------------------------------------------------------------- #


def test_upscale_label_describes_the_run(settings):
    from tasks.stage_orchestrator import _upscale_label

    resolved = upscale_options.from_payload(
        {"model": "4xNomos8kSC", "model_scale": 4, "gpu_id": 0, "tta": True}, settings
    )

    label = _upscale_label(resolved, settings)

    assert "4K" in label
    assert "4xNomos8kSC" in label
    assert "GPU 0" in label
    assert "TTA" in label


def test_upscale_label_uses_px_for_non_round_targets(settings):
    from tasks.stage_orchestrator import _upscale_label

    resolved = upscale_options.from_payload({"target_long_edge": 4500}, settings)

    assert "4500px" in _upscale_label(resolved, settings)


# --------------------------------------------------------------------------- #
# Source selection
# --------------------------------------------------------------------------- #


class FakeRecord:
    """Just enough of ``ImageRecord`` for the source-selection helper."""

    def __init__(self, record_id="rec1", working_path=None, original_path=None):
        self.id = record_id
        self.working_path = str(working_path) if working_path else None
        self.original_path = str(original_path) if original_path else None


def test_source_path_prefers_the_working_copy(tmp_path, settings):
    from tasks.stage_orchestrator import _upscale_source_path

    original = tmp_path / "original.jpg"
    working = tmp_path / "working.jpg"
    original.write_bytes(b"a")
    working.write_bytes(b"b")

    record = FakeRecord(working_path=working, original_path=original)

    assert _upscale_source_path(record, settings) == working


def test_source_path_falls_back_to_the_original(tmp_path, settings):
    from tasks.stage_orchestrator import _upscale_source_path

    original = tmp_path / "original.jpg"
    original.write_bytes(b"a")

    record = FakeRecord(working_path=tmp_path / "gone.jpg", original_path=original)

    assert _upscale_source_path(record, settings) == original


def test_source_path_never_reuses_a_previous_upscale(tmp_path, settings, monkeypatch):
    from tasks.stage_orchestrator import _upscale_source_path

    upscaled_dir = tmp_path / "upscaled"
    refined_dir = tmp_path / "refined"
    upscaled_dir.mkdir()
    refined_dir.mkdir()
    monkeypatch.setattr(settings, "UPSCALED_DIR", upscaled_dir)
    monkeypatch.setattr(settings, "REFINED_DIR", refined_dir)

    previous = upscaled_dir / "rec1-upscaled.jpg"
    previous.write_bytes(b"old upscale")
    refined = refined_dir / "rec1-refined.jpg"
    refined.write_bytes(b"refined")
    original = tmp_path / "original.jpg"
    original.write_bytes(b"original")

    # Re-running Stage 3 leaves working_path pointing at the previous output.
    record = FakeRecord(working_path=previous, original_path=original)

    # Feeding an upscale back into the model would inflate the file for no
    # added detail and make the before/after view compare an image to itself.
    assert _upscale_source_path(record, settings) == refined


def test_source_path_prefers_the_original_when_no_refined_copy_exists(
    tmp_path, settings, monkeypatch
):
    from tasks.stage_orchestrator import _upscale_source_path

    upscaled_dir = tmp_path / "upscaled"
    upscaled_dir.mkdir()
    monkeypatch.setattr(settings, "UPSCALED_DIR", upscaled_dir)
    monkeypatch.setattr(settings, "REFINED_DIR", tmp_path / "no-refined-here")

    previous = upscaled_dir / "rec1-upscaled.jpg"
    previous.write_bytes(b"old upscale")
    original = tmp_path / "original.jpg"
    original.write_bytes(b"original")

    record = FakeRecord(working_path=previous, original_path=original)

    assert _upscale_source_path(record, settings) == original


# --------------------------------------------------------------------------- #
# sRGB reporting honesty
# --------------------------------------------------------------------------- #
#
# ``srgb_embedded`` used to echo ``options.embed_srgb`` back to the caller. When
# the profile could not be built the encoder silently wrote an untagged JPEG, so
# the run detail claimed Adobe's colour-profile requirement was met while the
# file on disk had no profile at all. These tests pin the fix: the flag reports
# what is in the file, not what was requested.


def test_srgb_was_written_is_false_when_embedding_is_disabled(tmp_path, settings):
    import numpy as np

    from services.srgb_profile import write_srgb_jpeg

    destination = tmp_path / "tagged.jpg"
    write_srgb_jpeg(np.zeros((8, 8, 3), dtype=np.uint8), destination)
    disabled = upscale_options.from_payload({"embed_srgb": False}, settings)

    # The file is tagged, but the run did not ask for a profile, so the report
    # must not claim credit for one.
    assert runner._srgb_was_written(destination, disabled) is False


def test_srgb_was_written_reflects_an_untagged_file(tmp_path, settings):
    import cv2
    import numpy as np

    destination = tmp_path / "untagged.jpg"
    cv2.imwrite(str(destination), np.zeros((8, 8, 3), dtype=np.uint8))
    enabled = upscale_options.from_payload({"embed_srgb": True}, settings)

    # Requested but not delivered: this is exactly the case that used to lie.
    assert runner._srgb_was_written(destination, enabled) is False


def test_srgb_was_written_is_true_for_a_tagged_file(tmp_path, settings):
    import numpy as np

    from services.srgb_profile import write_srgb_jpeg

    destination = tmp_path / "tagged.jpg"
    write_srgb_jpeg(np.zeros((8, 8, 3), dtype=np.uint8), destination)
    enabled = upscale_options.from_payload({"embed_srgb": True}, settings)

    assert runner._srgb_was_written(destination, enabled) is True


def test_srgb_was_written_tolerates_a_missing_file(tmp_path, settings):
    enabled = upscale_options.from_payload({"embed_srgb": True}, settings)

    assert runner._srgb_was_written(tmp_path / "absent.jpg", enabled) is False


def test_resample_fallback_reports_the_embedded_profile(tmp_path, settings):
    """Force the resample path and prove the reported flag matches the file.

    ``executable=None`` skips the CLI probe, so this runs the encode logic
    without the neural binary and asserts the round trip end to end: the result
    claims an embedded profile *and* the file on disk really has one.
    """
    import numpy as np
    from PIL import Image

    from services.srgb_profile import has_srgb_profile

    source = tmp_path / "source.jpg"
    Image.fromarray(
        (np.random.default_rng(0).random((32, 24, 3)) * 255).astype("uint8"), mode="RGB"
    ).save(source, format="JPEG", quality=95)

    result = runner.upscale_image(
        source,
        tmp_path / "out",
        "rec-srgb",
        options=upscale_options.default_options(settings),
        settings=settings,
        executable=None,
    )

    assert result.success is True
    assert result.backend == runner.BACKEND_RESAMPLE
    assert result.srgb_embedded is True
    # The claim and the artefact must agree; this is the assertion that would
    # have failed while the profile builder was silently returning None.
    assert has_srgb_profile(result.output_path) is True
    with Image.open(result.output_path) as written:
        assert written.info.get("icc_profile")


def test_resample_fallback_is_honest_when_a_profile_is_not_requested(tmp_path, settings):
    """With embedding off, the report must not claim a profile."""
    import numpy as np
    from PIL import Image

    source = tmp_path / "source.jpg"
    Image.fromarray(
        (np.random.default_rng(1).random((32, 24, 3)) * 255).astype("uint8"), mode="RGB"
    ).save(source, format="JPEG", quality=95)

    result = runner.upscale_image(
        source,
        tmp_path / "out",
        "rec-plain",
        options=upscale_options.from_payload({"embed_srgb": False}, settings),
        settings=settings,
        executable=None,
    )

    assert result.success is True
    assert result.srgb_embedded is False
