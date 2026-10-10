"""Tests for the setup API — the HTTP contract the frontend modal is built on.

Every test asserts the **exact key sets** of the wire payload so a contract
drift (a renamed field, a dropped block) fails loudly here rather than
silently breaking the modal.  Like the engine tests, these are hermetic: no
network, no pip, no model downloads — the one end-to-end install test drives
the real engine through injected fakes.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import pytest

from services import model_installer, model_paths

TOP_KEYS = {"running", "install", "groups", "models", "environment", "probe"}
INSTALL_KEYS = {
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
GROUP_KEYS = {"key", "label", "size_mb", "installed", "version", "ready"}
MODEL_KEYS = {"models_dir", "rembg_dir", "hf_dir", "rembg_bytes", "hf_bytes", "env"}
ENV_KEYS = {
    "python",
    "venv",
    "torch",
    "transformers",
    "tokenizers",
    "onnxruntime_gpu",
    "opencv",
    "vitmatte_ready",
}


@pytest.fixture(autouse=True)
def fresh_installer(monkeypatch):
    """Every test starts from a pristine singleton (and restores the original)."""
    monkeypatch.setattr(model_installer, "_installer", model_installer.Installer())


@pytest.fixture()
def models_dir(tmp_path, monkeypatch):
    """Redirect the shared models tree so an install writes only into tmp."""
    monkeypatch.setattr(model_paths, "MODELS_DIR", tmp_path)
    return tmp_path


def test_get_dependencies_matches_the_wire_contract(client):
    response = client.get("/api/setup/dependencies")
    assert response.status_code == 200
    body = response.json()

    assert set(body) == TOP_KEYS
    assert body["running"] is False

    install = body["install"]
    assert set(install) == INSTALL_KEYS
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

    assert [(g["key"], g["label"], g["size_mb"]) for g in body["groups"]] == [
        ("torch-cpu", "PyTorch (CPU build)", 124.1),
        ("matting-stack", "ViTMatte runtime", 22.9),
        ("vitmatte-weights", "ViTMatte weights", 103.3),
    ]
    for group in body["groups"]:
        assert set(group) == GROUP_KEYS
        assert isinstance(group["installed"], bool)
        assert isinstance(group["ready"], bool)
        assert group["version"] is None or isinstance(group["version"], str)

    assert set(body["models"]) == MODEL_KEYS
    assert set(body["models"]["env"]) == {"U2NET_HOME", "REMBG_HOME", "HF_HOME"}
    assert isinstance(body["models"]["models_dir"], str)
    assert isinstance(body["models"]["rembg_bytes"], int)
    assert isinstance(body["models"]["hf_bytes"], int)

    environment = body["environment"]
    assert set(environment) == ENV_KEYS
    assert environment["python"] == platform.python_version()
    assert environment["venv"] == sys.executable
    assert isinstance(environment["vitmatte_ready"], bool)
    for key in ("torch", "transformers", "tokenizers", "onnxruntime_gpu", "opencv"):
        assert environment[key] is None or isinstance(environment[key], str)

    assert body["probe"] is None


def test_install_with_an_unknown_group_is_422(client):
    response = client.post("/api/setup/dependencies/install", json={"groups": ["nope"]})
    assert response.status_code == 422
    assert "unknown group" in response.json()["detail"].lower()


def test_install_with_an_empty_group_list_is_422(client):
    response = client.post("/api/setup/dependencies/install", json={"groups": []})
    assert response.status_code == 422
    assert response.json()["detail"] == "no groups requested"


def test_install_conflict_is_409_with_the_exact_detail(client, monkeypatch):
    def busy(groups):
        raise model_installer.AlreadyRunning("install already running")

    monkeypatch.setattr(model_installer, "start", busy)
    response = client.post("/api/setup/dependencies/install", json={"groups": ["torch-cpu"]})

    assert response.status_code == 409
    assert response.json() == {"detail": "install already running"}


def test_install_accepted_returns_202_with_the_status_payload(client, monkeypatch):
    captured: dict = {}

    def fake_start(groups):
        captured["groups"] = groups
        return model_installer.snapshot()

    monkeypatch.setattr(model_installer, "start", fake_start)
    response = client.post(
        "/api/setup/dependencies/install",
        json={"groups": ["torch-cpu", "vitmatte-weights"]},
    )

    assert response.status_code == 202
    body = response.json()
    assert set(body) == TOP_KEYS
    assert set(body["install"]) == INSTALL_KEYS
    assert captured["groups"] == ["torch-cpu", "vitmatte-weights"]


def test_cancel_when_idle_is_409_with_the_exact_detail(client):
    response = client.post("/api/setup/dependencies/cancel")

    assert response.status_code == 409
    assert response.json() == {"detail": "no install is running"}


def test_cancel_while_running_returns_200_status_payload(client):
    # Simulate an in-flight job; the autouse fixture restores a clean one.
    model_installer._installer._running = True

    response = client.post("/api/setup/dependencies/cancel")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == TOP_KEYS
    assert body["running"] is True


def test_probe_returns_a_probe_result(client, monkeypatch):
    result = {"ok": True, "ran_at": "2026-10-10T12:00:00", "output": "torch 2.6.0"}
    monkeypatch.setattr(model_installer, "run_probe", lambda: dict(result))

    response = client.post("/api/setup/dependencies/probe")

    assert response.status_code == 200
    assert response.json() == result


def test_install_runs_as_a_server_side_background_job(client, models_dir, monkeypatch):
    """POST returns immediately; the work finishes with the modal closed.

    The real engine runs on its background thread — only its network/process
    hooks are fakes, so this stays fully hermetic.
    """
    payload = b"streamed-wheel" * 16
    sha = hashlib.sha256(payload).hexdigest()
    url = "https://files.example/pkg/torch-2.6.0-cp311-cp311-win_amd64.whl"
    report = {
        "install": [
            {
                "name": "torch",
                "version": "2.6.0",
                "requested": True,
                "download_info": {"url": url, "archive_info": {"hashes": {"sha256": sha}}},
            }
        ]
    }

    def run_pip(args):
        if "--dry-run" in args:
            Path(args[args.index("--report") + 1]).write_text(
                json.dumps(report), encoding="utf-8"
            )
            return 0, "synthetic dry-run ok"
        return 0, "Successfully installed demo"

    def fetch(u: str):
        for start in range(0, len(payload), 64):
            yield payload[start : start + 64]

    installer = model_installer.Installer(
        head=lambda u: len(payload),
        fetch=fetch,
        run_pip=run_pip,
    )
    monkeypatch.setattr(model_installer, "_installer", installer)

    response = client.post("/api/setup/dependencies/install", json={"groups": ["torch-cpu"]})
    assert response.status_code == 202
    assert set(response.json()) == TOP_KEYS

    # Poll the status endpoint until the background job reaches a terminal state.
    body = response.json()
    for _ in range(300):
        body = client.get("/api/setup/dependencies").json()
        if body["install"]["state"] in {"done", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    install = body["install"]
    assert install["state"] == "done"
    assert install["percent"] == 100
    assert install["error"] is None
    assert install["groups"] == ["torch-cpu"]
    assert install["bytes_done"] == install["bytes_total"] == len(payload)
    assert install["started_at"] and install["finished_at"]
    assert install["log"][0] == "== Resolving =="
    assert install["log"][-1] == "all requested groups installed"
    assert body["running"] is False

    wheel_files = sorted(p.name for p in (models_dir / "wheels").iterdir())
    assert wheel_files == ["torch-2.6.0-cp311-cp311-win_amd64.whl"]
