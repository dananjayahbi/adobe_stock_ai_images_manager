"""Tests for the server-side dependency installer engine.

Hermetic by construction: **no network, no pip installs, no model downloads,
no inference**.  Every I/O seam (``head``/``fetch``/``run_pip``/``hf_download``)
is an injectable hook, and pip's ``--report`` is a synthetic JSON fixture fed
through the same code path the real one takes (including the UTF-8 read).

What is pinned here:

* the frozen ``GROUPS`` metadata (keys/labels/sizes are HTTP contract),
* ``_progress`` math including clamping and the unknown-total edge,
* ``_plan`` byte totals, satisfied-entry skipping and sha256 extraction,
* the log cap (500, newest last),
* the state machine: resolving -> downloading -> installing -> done, and the
  failed/cancelled branches (including "percent keeps its last value"),
* ``start()`` raising ``AlreadyRunning``/``UnknownGroup``, ``cancel()`` raising
  ``NotRunning``, and the cancel flag observed between files and between chunks,
* the probe script staying import-only (no ``from_pretrained``, no downloads).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import model_installer, model_paths

# --------------------------------------------------------------------------- #
# Fakes (the only "network" in this file)
# --------------------------------------------------------------------------- #


def make_entry(url: str, sha: str | None = None, name: str = "demo") -> dict:
    """One installable entry of a pip ``--report`` payload."""
    download_info: dict = {"url": url}
    if sha:
        download_info["archive_info"] = {"hashes": {"sha256": sha}}
    return {"name": name, "version": "1.0", "requested": True, "download_info": download_info}


def satisfied_entry(name: str = "already-satisfied") -> dict:
    """An entry with no URL: already satisfied locally, nothing to fetch."""
    return {"name": name, "version": "0.9", "download_info": None}


class FakePip:
    """Stand-in for ``run_pip``: writes a synthetic ``--report`` on dry-run."""

    def __init__(self, report: dict, fail_on: str | None = None, gate: threading.Event | None = None):
        self.report = report
        self.fail_on = fail_on  # "resolve" | "install" | None
        self.gate = gate
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(list(args))
        if "--dry-run" in args:
            if self.gate is not None:
                self.gate.wait(timeout=10)
            if self.fail_on == "resolve":
                return 1, "ERROR: no matching distribution"
            path = Path(args[args.index("--report") + 1])
            path.write_text(json.dumps(self.report, ensure_ascii=False), encoding="utf-8")
            return 0, "synthetic dry-run ok"
        if self.fail_on == "install":
            return 1, "ERROR: offline install exploded"
        return 0, "Successfully installed demo-1.0"


def stream(payload: bytes, chunk_size: int = 8):
    """A ``fetch`` that streams ``payload`` in fixed-size chunks."""
    fetch_calls: list[str] = []

    def fetch(url: str):
        fetch_calls.append(url)
        for start in range(0, len(payload), chunk_size):
            yield payload[start : start + chunk_size]

    fetch.calls = fetch_calls
    return fetch


@pytest.fixture()
def models_dir(tmp_path, monkeypatch):
    """Redirect the shared models tree into tmp_path (no repo pollution)."""
    monkeypatch.setattr(model_paths, "MODELS_DIR", tmp_path)
    return tmp_path


def join(installer) -> dict:
    installer._thread.join(timeout=10)
    assert not installer._thread.is_alive(), "installer thread did not finish"
    return installer.snapshot()


# --------------------------------------------------------------------------- #
# Frozen metadata & pure helpers
# --------------------------------------------------------------------------- #


def test_groups_metadata_matches_the_contract():
    assert list(model_installer.GROUPS) == [
        "torch-cpu",
        "matting-stack",
        "vitmatte-weights",
    ]
    torch_cpu = model_installer.GROUPS["torch-cpu"]
    assert torch_cpu.label == "PyTorch (CPU build)"
    assert torch_cpu.size_mb == 124.1
    assert torch_cpu.kind == "pip"
    assert torch_cpu.spec == ("torch",)

    matting = model_installer.GROUPS["matting-stack"]
    assert matting.label == "ViTMatte runtime"
    assert matting.size_mb == 22.9
    assert matting.spec == ("transformers",)

    weights = model_installer.GROUPS["vitmatte-weights"]
    assert weights.label == "ViTMatte weights"
    assert weights.size_mb == 103.3
    assert weights.kind == "huggingface"
    assert weights.repo == "hustvl/vitmatte-small-composition-1k"
    assert weights.allow_patterns == ("*.json", "*.txt", "*.safetensors")
    # The repo ships a duplicate pytorch_model.bin — allow_patterns excludes it.
    assert "*.bin" not in weights.allow_patterns

    with pytest.raises(dataclasses.FrozenInstanceError):
        torch_cpu.label = "mutated"  # type: ignore[misc]


def test_progress_formula_and_clamping():
    assert model_installer._progress(0, 0) == 0
    assert model_installer._progress(0, 1000) == 0
    assert model_installer._progress(250, 1000) == 25
    assert model_installer._progress(500, 1000) == 50
    # Clamped both ways.
    assert model_installer._progress(1500, 1000) == 100
    assert model_installer._progress(-10, 1000) == 0
    # Documented edge: unknown total (0) means any bytes read as full.
    assert model_installer._progress(50, 0) == 100


def test_plan_skips_satisfied_entries_and_computes_totals():
    url_a = "https://files.example/pkg/alpha-1.0.whl"
    url_b = "https://files.example/pkg/beta-2.0.whl"
    report = {
        "install": [
            make_entry(url_a, sha="a" * 64),
            make_entry(url_b),  # server gave no hash
            satisfied_entry(),
            {"name": "no-download-info"},  # nothing to fetch at all
        ]
    }
    sizes = {url_a: 1000, url_b: 2500}

    planned = model_installer._plan(report, lambda url: sizes[url])

    assert [p.filename for p in planned] == ["alpha-1.0.whl", "beta-2.0.whl"]
    assert [p.size for p in planned] == [1000, 2500]
    assert sum(p.size for p in planned) == 3500
    assert planned[0].sha256 == "a" * 64
    assert planned[1].sha256 is None


def test_plan_tolerates_a_failing_head():
    report = {"install": [make_entry("https://files.example/gone.whl")]}

    def head(url: str) -> int:
        raise RuntimeError("server refuses HEAD")

    planned = model_installer._plan(report, head)
    assert planned[0].size == 0  # unknown size, still planned


def test_plan_filename_strips_query_and_fragment():
    url = "https://files.example/pkg/gamma-3.0.whl?content-disposition=1#sha256=deadbeef"
    planned = model_installer._plan({"install": [make_entry(url)]}, lambda u: 7)
    assert planned[0].filename == "gamma-3.0.whl"


def test_pip_report_is_read_as_utf8(tmp_path):
    """pip writes UTF-8; a cp1252 read would mangle a name like törch."""
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps({"install": [make_entry("https://files.example/törch-2.6.whl")]}, ensure_ascii=False),
        encoding="utf-8",
    )

    report = model_installer._load_report(report_path)
    assert report["install"][0]["download_info"]["url"].endswith("/törch-2.6.whl")
    planned = model_installer._plan(report, lambda u: 1)
    assert planned[0].filename == "törch-2.6.whl"


def test_log_is_capped_at_500_newest_last(models_dir):
    assert model_installer.LOG_LIMIT == 500
    installer = model_installer.Installer()
    for index in range(600):
        installer._log(f"line {index}")

    log = installer.snapshot()["install"]["log"]
    assert len(log) == 500
    assert log[-1] == "line 599"
    assert log[0] == "line 100"


def test_idle_snapshot_has_the_exact_contract_shape(models_dir):
    snapshot = model_installer.Installer().snapshot()

    assert set(snapshot) == {
        "running",
        "install",
        "groups",
        "models",
        "environment",
        "probe",
    }
    assert set(snapshot["install"]) == {
        "state",
        "phase",
        "percent",
        "bytes_done",
        "bytes_total",
        "current_file",
        "groups",
        "error",
        "started_at",
        "finished_at",
        "log",
    }
    install = snapshot["install"]
    assert install["state"] == "idle"
    assert install["phase"] == "Idle"
    assert install["percent"] == 0
    assert install["bytes_done"] == 0
    assert install["bytes_total"] == 0
    assert install["current_file"] == ""
    assert install["groups"] == []
    assert install["error"] is None
    assert install["started_at"] is None
    assert install["finished_at"] is None
    assert install["log"] == []
    assert snapshot["running"] is False
    assert snapshot["probe"] is None

    assert [(g["key"], g["label"], g["size_mb"]) for g in snapshot["groups"]] == [
        ("torch-cpu", "PyTorch (CPU build)", 124.1),
        ("matting-stack", "ViTMatte runtime", 22.9),
        ("vitmatte-weights", "ViTMatte weights", 103.3),
    ]
    for group in snapshot["groups"]:
        assert set(group) == {"key", "label", "size_mb", "installed", "version", "ready"}

    assert set(snapshot["models"]) == {
        "models_dir",
        "rembg_dir",
        "hf_dir",
        "rembg_bytes",
        "hf_bytes",
        "env",
    }
    assert set(snapshot["models"]["env"]) == {"U2NET_HOME", "REMBG_HOME", "HF_HOME"}

    assert set(snapshot["environment"]) == {
        "python",
        "venv",
        "torch",
        "transformers",
        "tokenizers",
        "onnxruntime_gpu",
        "opencv",
        "vitmatte_ready",
    }


def test_detection_never_imports_the_heavy_packages(models_dir):
    """find_spec + metadata only — importing torch here would poison the suite."""
    model_installer.Installer().snapshot()
    assert "torch" not in sys.modules
    assert "transformers" not in sys.modules


# --------------------------------------------------------------------------- #
# Full pip-group runs (state machine, bytes, files, log)
# --------------------------------------------------------------------------- #


def test_pip_group_runs_to_done(models_dir):
    payload = b"wheel-bytes" * 64
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://files.example/pkg/torch-2.6.0-cp311-cp311-win_amd64.whl"
    pip = FakePip({"install": [make_entry(url, sha=sha, name="torch")]})
    installer = model_installer.Installer(
        head=lambda u: len(payload),
        fetch=stream(payload),
        run_pip=pip,
    )
    # Spy on every state transition the worker makes.
    seen: list[str] = []
    original = installer._set_state

    def spy(state: str, phase: str) -> None:
        seen.append(state)
        original(state, phase)

    installer._set_state = spy  # type: ignore[method-assign]

    installer.start(["torch-cpu"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert seen == ["resolving", "downloading", "installing", "done"]
    assert install["state"] == "done"
    assert install["phase"] == "Done"
    assert install["percent"] == 100
    assert install["error"] is None
    assert install["started_at"] and install["finished_at"]
    datetime.fromisoformat(install["started_at"])
    datetime.fromisoformat(install["finished_at"])
    assert snapshot["running"] is False
    assert install["current_file"] == ""
    assert install["groups"] == ["torch-cpu"]
    assert install["bytes_done"] == install["bytes_total"] == len(payload)

    log = install["log"]
    assert log[0] == "== Resolving =="
    assert log[-1] == "all requested groups installed"
    assert "== Downloading ==" in log
    assert "== Installing ==" in log
    assert "== Done ==" in log
    assert any(line.startswith("downloading ") for line in log)
    assert any(line.startswith("downloaded ") for line in log)

    # The wheel landed in the shared cache, no .part leftovers.
    entries = [p.name for p in (models_dir / "wheels").iterdir()]
    assert "torch-2.6.0-cp311-cp311-win_amd64.whl" in entries
    assert not any(name.endswith(".part") for name in entries)

    # Resolve was a dry-run with a report; install was offline from the cache.
    assert pip.calls[0][:3] == ["install", "--dry-run", "--quiet"]
    assert "--report" in pip.calls[0]
    assert pip.calls[1][:3] == ["install", "--no-index", "--find-links"]
    assert str(models_dir / "wheels") in pip.calls[1]
    assert len(pip.calls) == 2


def test_second_run_reuses_the_cached_wheel(models_dir):
    payload = b"cached-payload" * 32
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://files.example/pkg/transformers-4.50.0-py3-none-any.whl"
    pip = FakePip({"install": [make_entry(url, sha=sha)]})
    installer = model_installer.Installer(
        head=lambda u: len(payload),
        fetch=stream(payload),
        run_pip=pip,
    )

    installer.start(["matting-stack"])
    join(installer)
    installer.start(["matting-stack"])  # re-run: wheel is already on disk
    snapshot = join(installer)

    assert snapshot["install"]["state"] == "done"
    assert any(line.startswith("cached ") for line in snapshot["install"]["log"])
    # Second run still accounts for the bytes even though nothing streamed.
    assert snapshot["install"]["bytes_done"] == len(payload)


def test_sha_mismatch_fails_and_keeps_no_file(models_dir):
    payload = b"tampered-bytes"
    url = "https://files.example/pkg/transformers-4.50.0-py3-none-any.whl"
    pip = FakePip({"install": [make_entry(url, sha="0" * 64)]})
    installer = model_installer.Installer(
        head=lambda u: len(payload),
        fetch=stream(payload),
        run_pip=pip,
    )

    installer.start(["matting-stack"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert install["state"] == "failed"
    assert "sha256 mismatch" in (install["error"] or "")
    assert any("sha256 mismatch" in line for line in install["log"])
    # Failed before install: only the resolve call ran, nothing was written.
    assert len(pip.calls) == 1
    assert list((models_dir / "wheels").iterdir()) == []


def test_pip_resolve_failure_marks_failed(models_dir):
    pip = FakePip({}, fail_on="resolve")
    installer = model_installer.Installer(head=lambda u: 0, fetch=stream(b""), run_pip=pip)

    installer.start(["torch-cpu"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert install["state"] == "failed"
    assert "pip resolve failed (exit 1)" in (install["error"] or "")
    assert "ERROR: no matching distribution" in install["log"]
    assert install["finished_at"] is not None
    assert snapshot["running"] is False


def test_fetch_exception_marks_failed_and_keeps_last_percent(models_dir):
    """A dying thread must surface as state=failed, never a silent hang."""
    url = "https://files.example/pkg/transformers-4.50.0-py3-none-any.whl"
    pip = FakePip({"install": [make_entry(url)]})

    def fetch(u: str):
        yield b"A" * 50  # 50 of a planned 100 bytes -> percent 50
        raise RuntimeError("network exploded")

    installer = model_installer.Installer(head=lambda u: 100, fetch=fetch, run_pip=pip)
    installer.start(["matting-stack"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert install["state"] == "failed"
    assert install["error"] == "network exploded"
    assert any(line == "error: network exploded" for line in install["log"])
    # failed keeps the last value instead of snapping to 0 or 100.
    assert install["percent"] == 50
    # The partial .part file was cleaned up.
    assert not any((models_dir / "wheels").iterdir())


# --------------------------------------------------------------------------- #
# Cancellation
# --------------------------------------------------------------------------- #


def test_cancel_between_chunks_stops_mid_file(models_dir):
    url = "https://files.example/pkg/torch-2.6.0-cp311-cp311-win_amd64.whl"
    pip = FakePip({"install": [make_entry(url)]})
    installer = model_installer.Installer()  # bound later; fetch needs the reference

    def fetch(u: str):
        yield b"A" * 16
        installer._cancel.set()  # operator cancels while the file streams
        yield b"B" * 16

    installer._fetch = fetch  # type: ignore[assignment]
    installer._head = lambda u: 100  # type: ignore[assignment]
    installer._run_pip = pip  # type: ignore[assignment]

    installer.start(["torch-cpu"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert install["state"] == "cancelled"
    assert install["error"] is None
    assert install["finished_at"] is not None
    # percent keeps its last measured value: 16 of a planned 100 bytes.
    assert install["bytes_done"] == 16
    assert install["percent"] == 16
    assert "cancelled by operator" in install["log"]
    # Neither the wheel nor a partial was left behind.
    assert not any((models_dir / "wheels").iterdir())


def test_cancel_between_files_finishes_only_the_first(models_dir):
    url_a = "https://files.example/pkg/alpha-1.0.whl"
    url_b = "https://files.example/pkg/beta-2.0.whl"
    pip = FakePip({"install": [make_entry(url_a), make_entry(url_b, name="beta")]})
    installer = model_installer.Installer()
    calls: list[str] = []

    def fetch(u: str):
        calls.append(u)
        if len(calls) == 1:
            yield b"x" * 32
            installer._cancel.set()  # lands while file 1 finishes streaming
        else:  # pragma: no cover - must never be reached
            yield b"y" * 32

    installer._fetch = fetch  # type: ignore[assignment]
    installer._head = lambda u: 32  # type: ignore[assignment]
    installer._run_pip = pip  # type: ignore[assignment]

    installer.start(["torch-cpu"])
    snapshot = join(installer)

    assert snapshot["install"]["state"] == "cancelled"
    wheels = sorted(p.name for p in (models_dir / "wheels").iterdir())
    assert wheels == ["alpha-1.0.whl"]  # file 1 completed, file 2 never started
    assert len(pip.calls) == 1  # never reached the install phase


def test_cancel_during_resolve_aborts_before_planning(models_dir):
    gate = threading.Event()
    url = "https://files.example/pkg/torch-2.6.0-cp311-cp311-win_amd64.whl"
    pip = FakePip({"install": [make_entry(url)]}, gate=gate)
    head_calls: list[str] = []
    installer = model_installer.Installer(
        head=lambda u: head_calls.append(u) or 10,
        fetch=stream(b"unused"),
        run_pip=pip,
    )

    installer.start(["torch-cpu"])
    payload = installer.cancel()
    assert payload["running"] is True  # still winding down
    gate.set()
    snapshot = join(installer)

    assert snapshot["install"]["state"] == "cancelled"
    assert head_calls == []  # never HEAD-ed anything after the cancel
    assert len(pip.calls) == 1  # resolve only, no install
    assert snapshot["running"] is False


def test_cancel_when_idle_raises(models_dir):
    installer = model_installer.Installer()
    with pytest.raises(model_installer.NotRunning):
        installer.cancel()


# --------------------------------------------------------------------------- #
# start() guards
# --------------------------------------------------------------------------- #


def test_start_raises_already_running(models_dir):
    gate = threading.Event()
    url = "https://files.example/pkg/torch-2.6.0-cp311-cp311-win_amd64.whl"
    pip = FakePip({"install": [make_entry(url)]}, gate=gate)
    installer = model_installer.Installer(
        head=lambda u: 8,
        fetch=stream(b"payload"),
        run_pip=pip,
    )

    installer.start(["torch-cpu"])
    with pytest.raises(model_installer.AlreadyRunning):
        installer.start(["matting-stack"])
    # The rejected call must not have rewritten the in-flight job's groups.
    assert installer.snapshot()["install"]["groups"] == ["torch-cpu"]

    gate.set()
    snapshot = join(installer)
    assert snapshot["install"]["state"] == "done"
    assert snapshot["running"] is False


def test_start_rejects_unknown_and_empty_groups(models_dir):
    installer = model_installer.Installer()
    with pytest.raises(model_installer.UnknownGroup):
        installer.start(["torch-cpu", "no-such-group"])
    with pytest.raises(model_installer.UnknownGroup):
        installer.start([])
    snapshot = installer.snapshot()
    assert snapshot["running"] is False
    assert snapshot["install"]["state"] == "idle"


# --------------------------------------------------------------------------- #
# Hugging Face group
# --------------------------------------------------------------------------- #


def test_hf_group_downloads_weights(models_dir):
    downloaded: dict = {}

    def fake_hf(repo_id, allow_patterns, local_dir, on_progress):
        downloaded["repo_id"] = repo_id
        downloaded["patterns"] = allow_patterns
        (local_dir / "model.safetensors").write_bytes(b"w" * 2048)
        on_progress()

    installer = model_installer.Installer(hf_download=fake_hf)
    installer.start(["vitmatte-weights"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert downloaded["repo_id"] == "hustvl/vitmatte-small-composition-1k"
    assert downloaded["patterns"] == ["*.json", "*.txt", "*.safetensors"]
    assert install["state"] == "done"
    assert install["percent"] == 100
    assert install["bytes_done"] == 2048
    assert (models_dir / "huggingface-vitmatte" / "model.safetensors").is_file()

    weights_group = next(
        g for g in snapshot["groups"] if g["key"] == "vitmatte-weights"
    )
    assert weights_group["installed"] is True
    assert weights_group["ready"] is True
    assert weights_group["version"] is None


def test_hf_group_falls_back_to_counting_files(models_dir):
    def silent_hf(repo_id, allow_patterns, local_dir, on_progress):
        # Simulates a hub version where the progress callback never fires.
        (local_dir / "model.safetensors").write_bytes(b"w" * 512)

    installer = model_installer.Installer(hf_download=silent_hf)
    installer.start(["vitmatte-weights"])
    snapshot = join(installer)
    install = snapshot["install"]

    assert install["state"] == "done"
    assert install["bytes_done"] == 512  # read from disk after the fact
    assert any("counted 1 file(s)" in line for line in install["log"])


def test_progress_tqdm_reports_only_byte_denominated_bars():
    """The tqdm stand-in must not let the file-count bar corrupt byte progress."""
    calls: list[int] = []
    progress_cls = model_installer._make_progress_tqdm(lambda: calls.append(1))

    byte_bar = progress_cls(
        desc="Downloading bytes", total=0, initial=0, unit="B", unit_scale=True, bar_format="{}"
    )
    file_bar = progress_cls(desc="Fetching 3 files", total=3)

    byte_bar.update(1024)
    assert len(calls) == 1  # first byte update reports immediately
    file_bar.update(1)
    file_bar.close()
    assert len(calls) == 1  # file-count bar must stay silent
    byte_bar.close()
    assert len(calls) == 2  # close flushes a final byte report
    assert byte_bar.n == 1024
    assert byte_bar.format_dict["rate"] is None
    byte_bar.set_description_str("done")
    byte_bar.set_description("done")
    byte_bar.set_postfix_str("x")
    byte_bar.refresh()
    with progress_cls(desc="ctx", total=1, unit="B") as in_ctx:
        in_ctx.update(1)
    # update() reports (3), __exit__ -> close() flushes a final one (4).
    assert len(calls) == 4


# --------------------------------------------------------------------------- #
# Probe
# --------------------------------------------------------------------------- #


def test_probe_script_is_import_only():
    script = model_installer.PROBE_SCRIPT
    assert "from_pretrained" not in script
    assert "snapshot_download" not in script
    assert "torch.__version__" in script
    assert "transformers.__version__" in script
    assert "VitMatteForImageMatting" in script
    assert "VitMatteImageProcessorPil" in script
    assert "VitMatteImageProcessor" in script
    assert "sys.exit" in script


def test_run_probe_reports_success(monkeypatch):
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="torch 2.6.0\ntransformers 4.50.0\nVitMatteForImageMatting: ok\n"
            "processor: VitMatteImageProcessorPil\n",
            stderr="",
        )

    monkeypatch.setattr(model_installer.subprocess, "run", fake_run)
    installer = model_installer.Installer()
    result = installer.run_probe()

    assert set(result) == {"ok", "ran_at", "output"}
    assert result["ok"] is True
    assert "torch 2.6.0" in result["output"]
    datetime.fromisoformat(result["ran_at"])  # ISO-8601
    assert seen["cmd"][0] == sys.executable
    assert seen["cmd"][1] == "-c"
    assert seen["cmd"][2] == model_installer.PROBE_SCRIPT
    assert seen["kwargs"]["timeout"] == 120
    assert seen["kwargs"]["capture_output"] is True
    # The result is surfaced through the status payload too.
    assert installer.snapshot()["probe"] == result


def test_run_probe_failure_is_data_not_an_exception(monkeypatch):
    def fake_run(cmd, **kwargs):
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="probe failed: cannot import torch/transformers: No module named 'torch'",
        )

    monkeypatch.setattr(model_installer.subprocess, "run", fake_run)
    result = model_installer.Installer().run_probe()

    assert result["ok"] is False
    assert "No module named 'torch'" in result["output"]


def test_run_probe_timeout_becomes_a_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise model_installer.subprocess.TimeoutExpired(cmd=cmd, timeout=120)

    monkeypatch.setattr(model_installer.subprocess, "run", fake_run)
    result = model_installer.Installer().run_probe()

    assert result["ok"] is False
    assert "timed out after 120s" in result["output"]
