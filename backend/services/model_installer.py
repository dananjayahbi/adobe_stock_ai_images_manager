"""Server-side installer for the heavy optional runtime dependencies.

PyTorch and the ViTMatte stack are hundreds of megabytes, so they are **not**
part of ``requirements.txt``.  An operator downloads them from the frontend
Setup modal, but the download itself is a *server-side background job*: the
modal only renders this module's state, and closing it does not stop the work.

State machine (``InstallState.state``)::

    idle -> resolving -> downloading -> installing -> done
                          ^     |           |
                          +-----+-----------+--> cancelled   (operator)
                                 +----------------> failed    (any error)

``percent`` semantics — honest about what is actually measured:

* ``idle`` / ``resolving``  -> 0. Nothing is being downloaded yet.
* ``downloading``           -> ``int(100 * bytes_done / max(bytes_total, 1))``
  clamped to 0..100.  ``bytes_total`` is the sum of the ``Content-Length``
  sizes gathered by HEAD-ing every planned URL (the HF group uses its size
  estimate).  When the total is genuinely unknown (0) any bytes read as 100 —
  that is why the plan step exists.
* ``installing`` / ``done`` -> 100. pip runs offline from the local wheel
  cache; there is nothing left to measure.
* ``failed`` / ``cancelled``-> the **last** value, so the bar never lies about
  how far the run got before it stopped.

Each pip group runs its own ``resolve -> download -> install`` cycle, so with
several groups the bar tracks the group currently in flight.

The job is a singleton ``threading.Thread(daemon=True)`` guarded by a
``threading.Lock``: a second ``start()`` raises ``AlreadyRunning``.  Cancel is
cooperative — the flag is checked between groups, between files, and between
chunks (a running pip subprocess or HF snapshot call runs to its next
boundary).

All network/process access (``head``/``fetch``/``run_pip``/``hf_download``)
goes through injectable hooks so tests are hermetic: no network, no pip, no
model downloads.  Downloaded wheels are cached in ``<repo>/models/wheels`` —
inside the same shareable ``models/`` tree as the weights — so a re-install
is fully offline.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import requests

from services import model_paths

logger = logging.getLogger(__name__)

#: Newest-last cap for the install log.
LOG_LIMIT = 500

#: Where wheels land (download cache, ``--find-links`` source).
WHEELS_DIRNAME = "wheels"

#: Where the ViTMatte snapshot lands (checked by the weights group).
WEIGHTS_DIRNAME = "huggingface-vitmatte"

#: Probe subprocess budget.
PROBE_TIMEOUT = 120


class AlreadyRunning(Exception):
    """``start()`` was called while a job is already in flight (HTTP 409)."""


class NotRunning(Exception):
    """``cancel()`` was called while no job is running (HTTP 409)."""


class UnknownGroup(Exception):
    """An install group key that is not in :data:`GROUPS` (HTTP 422)."""


class InstallError(Exception):
    """A phase failed (pip non-zero exit, sha mismatch, ...)."""


class _Cancelled(Exception):
    """Internal: the cancel flag was observed at a safe boundary."""


@dataclass(frozen=True)
class Group:
    """Frozen metadata for one install group."""

    key: str
    label: str
    kind: str  # "pip" | "huggingface"
    size_mb: float
    spec: tuple[str, ...] = ()
    repo: str | None = None
    allow_patterns: tuple[str, ...] = ()

    @property
    def est_bytes(self) -> int:
        """Advertised size in bytes (display estimate, not a guarantee)."""
        return int(round(self.size_mb * 1_000_000))


#: Exact install groups — keys, labels and sizes are part of the HTTP contract.
GROUPS: dict[str, Group] = {
    group.key: group
    for group in (
        Group(
            key="torch-cpu",
            label="PyTorch (CPU build)",
            kind="pip",
            size_mb=124.1,
            spec=("torch",),
        ),
        Group(
            key="matting-stack",
            label="ViTMatte runtime",
            kind="pip",
            size_mb=22.9,
            spec=("transformers",),
        ),
        Group(
            key="vitmatte-weights",
            label="ViTMatte weights",
            kind="huggingface",
            size_mb=103.3,
            repo="hustvl/vitmatte-small-composition-1k",
            # The repo also ships a duplicate ``pytorch_model.bin``; the
            # allow-list keeps only the small configs and the safetensors.
            allow_patterns=("*.json", "*.txt", "*.safetensors"),
        ),
    )
}


@dataclass(frozen=True)
class PlannedFile:
    """One file the downloader will fetch, straight from a pip ``--report``."""

    url: str
    filename: str
    size: int
    sha256: str | None = None


@dataclass
class _InstallState:
    """Mutable install state; serialized to the exact ``InstallState`` shape."""

    state: str = "idle"
    phase: str = "Idle"
    percent: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    current_file: str = ""
    groups: list[str] = field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    log: list[str] = field(default_factory=list)


#: The probe runs in a subprocess so a failed import cannot poison the server.
#: It only *imports* and prints — no ``from_pretrained``, no downloads, no
#: inference — and exits non-zero with a clear message when anything is missing.
PROBE_SCRIPT = """
import sys


def main() -> int:
    try:
        import torch
        import transformers
    except Exception as exc:
        print(f"probe failed: cannot import torch/transformers: {exc}", file=sys.stderr)
        return 1
    print(f"torch {torch.__version__}")
    print(f"transformers {transformers.__version__}")

    try:
        from transformers import VitMatteForImageMatting
    except Exception as exc:
        print(f"probe failed: VitMatteForImageMatting unavailable: {exc}", file=sys.stderr)
        return 1
    print("VitMatteForImageMatting: ok")

    try:
        from transformers import VitMatteImageProcessorPil as _Processor
        print("processor: VitMatteImageProcessorPil")
    except Exception:
        try:
            from transformers import VitMatteImageProcessor as _Processor
        except Exception as exc:
            print(f"probe failed: no VitMatte image processor: {exc}", file=sys.stderr)
            return 1
        print("processor: VitMatteImageProcessor")
    return 0


sys.exit(main())
"""


# --------------------------------------------------------------------------- #
# Pure helpers (unit-tested without any I/O)
# --------------------------------------------------------------------------- #

def _progress(done: int, total: int) -> int:
    """Percent from byte counts, clamped to 0..100.

    ``max(total, 1)`` matches the documented formula: an unknown total (0)
    means any progress reads as full — the plan step exists to avoid that.
    """
    return max(0, min(100, int(100 * done / max(total, 1))))


def _plan(report: dict, head: Callable[[str], int]) -> list[PlannedFile]:
    """Turn a pip ``--report`` payload into a download plan.

    Pure apart from the injected ``head(url) -> int`` callable, which returns
    ``Content-Length`` (0 when unknown or unreachable).  Entries without a
    ``download_info.url`` are already satisfied locally — nothing to fetch.
    A ``sha256`` expectation is taken from
    ``download_info.archive_info.hashes.sha256`` when pip provided one.
    """
    planned: list[PlannedFile] = []
    for index, entry in enumerate(report.get("install") or []):
        download = entry.get("download_info") or {}
        url = download.get("url")
        if not url:
            continue
        clean = url.split("#", 1)[0].split("?", 1)[0]
        filename = clean.rsplit("/", 1)[-1] or f"download-{index}.bin"
        archive = download.get("archive_info") or {}
        sha256 = (archive.get("hashes") or {}).get("sha256")
        try:
            size = int(head(url))
        except Exception:
            size = 0
        planned.append(
            PlannedFile(url=url, filename=filename, size=max(size, 0), sha256=sha256)
        )
    return planned


def _load_report(path: str | Path) -> dict:
    """Read pip's ``--report`` JSON.

    The encoding is pinned to UTF-8: pip writes UTF-8, and ``open()`` on
    Windows would otherwise decode with the ANSI codepage (cp1252) and mangle
    non-ASCII wheel names.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _now() -> str:
    """ISO-8601 timestamp for ``started_at``/``finished_at``/``ran_at``."""
    return datetime.now().isoformat(timespec="seconds")


def _folder_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(1 for f in path.rglob("*") if f.is_file())


def _find_spec(name: str) -> bool:
    """Is a top-level module importable? Never imports it (no heavy side effects)."""
    import importlib.util

    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _dist_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def weights_dir() -> Path:
    """Where the ViTMatte snapshot lives — resolved at call time so tests can redirect it."""
    return model_paths.MODELS_DIR / WEIGHTS_DIRNAME


def wheels_dir() -> Path:
    """Download cache for wheels (also pip's ``--find-links`` source)."""
    return model_paths.MODELS_DIR / WHEELS_DIRNAME


def weights_ready() -> bool:
    """True when ``models/huggingface-vitmatte`` exists and holds a ``.safetensors`` file."""
    directory = weights_dir()
    if not directory.is_dir():
        return False
    return any(directory.rglob("*.safetensors"))


def environment() -> dict:
    """Interpreter + distribution facts — detected without importing torch/transformers."""
    torch_ok = _find_spec("torch")
    transformers_ok = _find_spec("transformers")
    return {
        "python": platform.python_version(),
        "venv": sys.executable,
        "torch": _dist_version("torch"),
        "transformers": _dist_version("transformers"),
        "tokenizers": _dist_version("tokenizers"),
        "onnxruntime_gpu": _dist_version("onnxruntime-gpu"),
        "opencv": _dist_version("opencv-python-headless"),
        # "Can ViTMatte actually run here?" needs runtime *and* weights.
        "vitmatte_ready": torch_ok and transformers_ok and weights_ready(),
    }


def group_status(group: Group) -> dict:
    """Per-group ``installed``/``version``/``ready`` without importing anything heavy."""
    if group.kind == "huggingface":
        installed = weights_ready()
        version = None
    else:
        installed = _find_spec(group.spec[0])
        version = _dist_version(group.spec[0])
    return {
        "key": group.key,
        "label": group.label,
        "size_mb": group.size_mb,
        "installed": installed,
        "version": version,
        "ready": installed,
    }


# --------------------------------------------------------------------------- #
# Default (production) hooks — all network/process access lives here
# --------------------------------------------------------------------------- #

def _default_head(url: str) -> int:
    """``Content-Length`` for a URL; 0 when the server will not say."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=30)
        if response.status_code >= 400:
            # Some hosts reject HEAD outright; a 1-byte ranged GET still
            # reports the full size via Content-Range.
            response.close()
            response = requests.get(
                url,
                stream=True,
                allow_redirects=True,
                timeout=30,
                headers={"Range": "bytes=0-0"},
            )
        try:
            if response.status_code >= 400:
                return 0
            total = response.headers.get("Content-Length", "")
            content_range = response.headers.get("Content-Range", "")
            if "/" in content_range:
                candidate = content_range.rsplit("/", 1)[-1]
                if candidate.isdigit():
                    total = candidate
            return int(total) if total.isdigit() else 0
        finally:
            response.close()
    except Exception:
        return 0


def _default_fetch(url: str) -> Iterator[bytes]:
    """Stream a URL as chunks; ``raise_for_status`` fires on first iteration."""
    response = requests.get(url, stream=True, timeout=(15, 120))
    response.raise_for_status()
    try:
        for chunk in response.iter_content(chunk_size=256 * 1024):
            if chunk:
                yield chunk
    finally:
        response.close()


def _default_run_pip(args: list[str]) -> tuple[int, str]:
    """Run the venv's pip with ``args``; return (exit code, merged stdout+stderr)."""
    command = [sys.executable, "-m", "pip", *args]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stdout = (proc.stdout or "").rstrip("\n")
    stderr = (proc.stderr or "").rstrip("\n")
    merged = "\n".join(part for part in (stdout, stderr) if part)
    return proc.returncode, merged


def _make_progress_tqdm(on_progress: Callable[[], None]) -> type:
    """Build a minimal tqdm look-alike that feeds byte progress to ``on_progress``.

    huggingface-hub's ``snapshot_download(tqdm_class=...)`` constructs bars with
    tqdm-compatible kwargs (``desc``/``total``/``initial``/``unit``/``unit_scale``/
    ``bar_format``) and then calls ``update``/``refresh``/``close``/
    ``set_description``/``set_description_str``/``set_postfix_str``/``format_dict``.
    Only bars denominated in bytes (``unit="B"``) report — the per-file-count
    map bar must not corrupt byte progress.  Reports are throttled because
    ``update()`` fires per chunk; the caller does one final read of the folder
    anyway.
    """

    class _ProgressTqdm:
        def __init__(self, *args, **kwargs):
            self.desc = kwargs.get("desc") or ""
            self.total = kwargs.get("total")
            self.n = int(kwargs.get("initial") or 0)
            self._is_bytes = kwargs.get("unit") == "B"
            self._last_report = 0.0

        def update(self, n: int = 1) -> None:
            self.n += int(n or 0)
            if self._is_bytes:
                now = time.monotonic()
                if now - self._last_report >= 0.1:
                    self._last_report = now
                    on_progress()

        def refresh(self) -> None:
            pass

        def close(self) -> None:
            if self._is_bytes:
                on_progress()

        def set_description(self, desc=None, refresh: bool = True) -> None:
            self.desc = desc or ""

        def set_description_str(self, desc, refresh: bool = True) -> None:
            self.desc = desc or ""

        def set_postfix_str(self, s, refresh: bool = True) -> None:
            pass

        @property
        def format_dict(self) -> dict:
            return {"n": self.n, "total": self.total, "rate": None}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            self.close()
            return False

        def __str__(self) -> str:
            return f"{self.desc}: {self.n}/{self.total}"

    return _ProgressTqdm


def _default_hf_download(
    repo_id: str,
    allow_patterns: list[str],
    local_dir: Path,
    on_progress: Callable[[], None] | None = None,
) -> None:
    """``snapshot_download`` wired for live progress, with a plain fallback.

    The progress path passes a tqdm stand-in whose byte bars trigger
    ``on_progress`` (which re-reads *partial file sizes* from disk).  If the
    hub's progress interface is unavailable or a future version's contract
    shifts, fall back to a plain ``snapshot_download`` — progress then arrives
    once, from the final folder size, instead of failing the install.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - hub is a base dependency
        raise InstallError(f"huggingface-hub is not installed: {exc}") from exc

    kwargs = {
        "repo_id": repo_id,
        "allow_patterns": list(allow_patterns),
        "local_dir": str(local_dir),
    }
    if on_progress is not None and "tqdm_class" in inspect.signature(snapshot_download).parameters:
        try:
            snapshot_download(tqdm_class=_make_progress_tqdm(on_progress), **kwargs)
            on_progress()
            return
        except Exception as exc:
            logger.warning("live HF progress unavailable (%s); retrying without it", exc)
    snapshot_download(**kwargs)
    if on_progress is not None:
        on_progress()


# --------------------------------------------------------------------------- #
# The installer
# --------------------------------------------------------------------------- #

class Installer:
    """Singleton-capable background installer: progress state + worker thread."""

    def __init__(
        self,
        *,
        head: Callable[[str], int] | None = None,
        fetch: Callable[[str], Iterator[bytes]] | None = None,
        run_pip: Callable[[list[str]], tuple[int, str]] | None = None,
        hf_download: Callable[..., None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._running = False
        self._probe: dict | None = None
        self._st = _InstallState()
        # Injectable hooks: tests drive these with fakes (no network/pip).
        self._head = head if head is not None else _default_head
        self._fetch = fetch if fetch is not None else _default_fetch
        self._run_pip = run_pip if run_pip is not None else _default_run_pip
        self._hf_download = hf_download if hf_download is not None else _default_hf_download

    # -- state plumbing ----------------------------------------------------- #

    def _log(self, message: str) -> None:
        """Append one line, newest last, capped at ``LOG_LIMIT``."""
        with self._lock:
            self._st.log.append(str(message))
            overflow = len(self._st.log) - LOG_LIMIT
            if overflow > 0:
                del self._st.log[:overflow]

    def _set_state(self, state: str, phase: str) -> None:
        with self._lock:
            st = self._st
            st.state = state
            st.phase = phase
            if state in ("idle", "resolving"):
                st.percent = 0
            elif state in ("installing", "done"):
                st.percent = 100
            # downloading: percent is driven by _set_bytes/_bump_bytes;
            # failed/cancelled: keep the last value (documented semantics).
        self._log(f"== {phase} ==")

    def _set_bytes(self, done: int, total: int | None = None) -> None:
        with self._lock:
            st = self._st
            st.bytes_done = max(0, int(done))
            if total is not None:
                st.bytes_total = max(0, int(total))
            if st.state == "downloading":
                st.percent = _progress(st.bytes_done, st.bytes_total)

    def _bump_bytes(self, delta: int) -> None:
        with self._lock:
            st = self._st
            st.bytes_done += int(delta)
            if st.state == "downloading":
                st.percent = _progress(st.bytes_done, st.bytes_total)

    def _log_output(self, output: str) -> None:
        for line in (output or "").splitlines():
            line = line.rstrip()
            if line:
                self._log(line)

    # -- public API --------------------------------------------------------- #

    def snapshot(self) -> dict:
        """Full status payload for the HTTP contract (see module docstring)."""
        with self._lock:
            st = self._st
            install = {
                "state": st.state,
                "phase": st.phase,
                "percent": st.percent,
                "bytes_done": st.bytes_done,
                "bytes_total": st.bytes_total,
                "current_file": st.current_file,
                "groups": list(st.groups),
                "error": st.error,
                "started_at": st.started_at,
                "finished_at": st.finished_at,
                "log": list(st.log),
            }
            running = self._running
            probe = dict(self._probe) if self._probe else None
        return {
            "running": running,
            "install": install,
            "groups": [group_status(g) for g in GROUPS.values()],
            "models": model_paths.describe(),
            "environment": environment(),
            "probe": probe,
        }

    def start(self, groups: list[str]) -> dict:
        """Begin installing ``groups`` on a background thread.

        Raises ``UnknownGroup`` for an empty or unknown list and
        ``AlreadyRunning`` when a job is already in flight.  The returned
        payload is taken immediately — the job continues server-side.
        """
        if not groups:
            raise UnknownGroup("no groups requested")
        unknown = [key for key in groups if key not in GROUPS]
        if unknown:
            raise UnknownGroup("unknown group(s): " + ", ".join(unknown))
        with self._lock:
            if self._running:
                raise AlreadyRunning("install already running")
            st = self._st
            # Fresh job, fresh log: the modal tells this run's story only.
            st.groups = list(groups)
            st.error = None
            st.started_at = _now()
            st.finished_at = None
            st.bytes_done = 0
            st.bytes_total = 0
            st.current_file = ""
            st.log = []
            self._cancel.clear()
            self._running = True
        self._set_state("resolving", "Resolving")
        thread = threading.Thread(
            target=self._run,
            args=(list(groups),),
            name="model-installer",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        thread.start()
        return self.snapshot()

    def cancel(self) -> dict:
        """Request cooperative cancellation; raises ``NotRunning`` when idle.

        The payload reflects the state *now* — the worker flips to
        ``cancelled`` at its next file/chunk boundary.
        """
        with self._lock:
            if not self._running:
                raise NotRunning("no install is running")
            self._cancel.set()
        self._log("cancel requested")
        return self.snapshot()

    def run_probe(self) -> dict:
        """Import-check torch/transformers/ViTMatte in a *subprocess*.

        The subprocess (``timeout=120``) means a failed or hanging import
        cannot poison the server process.  The script only imports and prints
        — no ``from_pretrained``, no weight download, no inference.
        """
        try:
            proc = subprocess.run(
                [sys.executable, "-c", PROBE_SCRIPT],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=PROBE_TIMEOUT,
            )
            stdout = (proc.stdout or "").rstrip()
            stderr = (proc.stderr or "").rstrip()
            output = "\n".join(part for part in (stdout, stderr) if part)
            ok = proc.returncode == 0
            if not output:
                output = "probe ran without output" if ok else f"probe exited with status {proc.returncode}"
        except subprocess.TimeoutExpired:
            ok = False
            output = f"probe timed out after {PROBE_TIMEOUT}s"
        except Exception as exc:
            ok = False
            output = str(exc) or exc.__class__.__name__
        result = {"ok": ok, "ran_at": _now(), "output": output}
        with self._lock:
            self._probe = dict(result)
        return dict(result)

    # -- worker ------------------------------------------------------------- #

    def _run(self, groups: list[str]) -> None:
        """Thread body: run each group, then land on done/failed/cancelled."""
        try:
            for key in groups:
                if self._cancel.is_set():
                    raise _Cancelled()
                group = GROUPS[key]
                if group.kind == "pip":
                    self._run_pip_group(group)
                else:
                    self._run_hf_group(group)
            with self._lock:
                self._st.finished_at = _now()
            self._set_state("done", "Done")
            self._log("all requested groups installed")
        except _Cancelled:
            with self._lock:
                self._st.finished_at = _now()
            self._set_state("cancelled", "Cancelled")
            self._log("cancelled by operator")
        except Exception as exc:  # never let the thread die silently
            message = str(exc) or exc.__class__.__name__
            with self._lock:
                self._st.finished_at = _now()
                self._st.error = message
            self._set_state("failed", "Failed")
            self._log(f"error: {message}")
        finally:
            with self._lock:
                self._running = False
            self._cancel.clear()

    def _run_pip_group(self, group: Group) -> None:
        spec = list(group.spec)
        with self._lock:
            already_resolving = self._st.state == "resolving"
        if not already_resolving:
            self._set_state("resolving", "Resolving")

        # 1. Resolve: what would pip install, and from where?
        self._log(f"[{group.label}] resolving: pip install --dry-run {' '.join(spec)}")
        handle, report_path = tempfile.mkstemp(prefix="pip-report-", suffix=".json")
        os.close(handle)
        try:
            code, output = self._run_pip(
                ["install", "--dry-run", "--quiet", "--report", report_path, *spec]
            )
            self._log_output(output)
            if code != 0:
                raise InstallError(f"pip resolve failed (exit {code}) for {' '.join(spec)}")
            report = _load_report(report_path)
        finally:
            Path(report_path).unlink(missing_ok=True)

        if self._cancel.is_set():
            raise _Cancelled()

        # 2. Plan: HEAD every URL for its size; skip already-satisfied entries.
        planned = _plan(report, self._head)
        total = sum(item.size for item in planned)
        self._set_bytes(0, total)
        self._log(f"[{group.label}] plan: {len(planned)} file(s), {total} bytes")

        # 3. Download into the shared wheel cache, verifying sha256 when given.
        self._set_state("downloading", "Downloading")
        wheels_dir().mkdir(parents=True, exist_ok=True)
        for item in planned:
            if self._cancel.is_set():
                raise _Cancelled()
            self._download_one(item)
        with self._lock:
            self._st.current_file = ""
        if self._cancel.is_set():
            raise _Cancelled()

        # 4. Install offline from the cache.
        self._set_state("installing", "Installing")
        self._log(f"[{group.label}] installing {' '.join(spec)} from {wheels_dir()}")
        code, output = self._run_pip(
            ["install", "--no-index", "--find-links", str(wheels_dir()), *spec]
        )
        self._log_output(output)
        if code != 0:
            raise InstallError(f"pip install failed (exit {code}) for {' '.join(spec)}")
        self._log(f"[{group.label}] installed")

    def _download_one(self, item: PlannedFile) -> None:
        target = wheels_dir() / item.filename
        part = target.with_name(target.name + ".part")
        with self._lock:
            self._st.current_file = item.filename
        if target.exists() and self._cache_usable(target, item):
            size = target.stat().st_size
            self._bump_bytes(size)
            self._log(f"cached {item.filename} ({size} bytes)")
            return
        suffix = f" ({item.size} bytes)" if item.size else ""
        self._log(f"downloading {item.filename}{suffix}")
        digest = hashlib.sha256()
        written = 0
        try:
            with open(part, "wb") as handle:
                for chunk in self._fetch(item.url):
                    if self._cancel.is_set():
                        raise _Cancelled()
                    handle.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    self._bump_bytes(len(chunk))
            if item.sha256:
                actual = digest.hexdigest()
                if actual.lower() != item.sha256.lower():
                    message = (
                        f"sha256 mismatch for {item.filename}: "
                        f"expected {item.sha256}, got {actual}"
                    )
                    part.unlink(missing_ok=True)
                    self._log(message)
                    raise InstallError(message)
            part.replace(target)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        self._log(f"downloaded {item.filename} ({written} bytes)")

    @staticmethod
    def _cache_usable(target: Path, item: PlannedFile) -> bool:
        """A cached wheel counts only when it still matches the plan."""
        size = target.stat().st_size
        if item.sha256:
            digest = hashlib.sha256()
            with open(target, "rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            return digest.hexdigest().lower() == item.sha256.lower()
        if item.size:
            return size == item.size
        return size > 0

    def _run_hf_group(self, group: Group) -> None:
        target = weights_dir()
        target.mkdir(parents=True, exist_ok=True)
        self._set_state("downloading", "Downloading")
        with self._lock:
            self._st.bytes_done = 0
            self._st.bytes_total = group.est_bytes
            self._st.percent = _progress(0, group.est_bytes)
            # A snapshot has no single filename to show, so the repo id stands
            # in — otherwise the modal would sit next to an empty file name.
            self._st.current_file = group.repo or ""
        self._log(f"[{group.label}] downloading {group.repo} -> {target}")

        callback_fired = False

        def on_progress() -> None:
            nonlocal callback_fired
            callback_fired = True
            # Live view of *partial file sizes* on disk (safe mid-write).
            self._set_bytes(_folder_bytes(target))

        # The hub's progress plumbing has moved between versions and is not
        # always reachable, so sample the folder on a watcher thread regardless.
        # Relying on it alone left a 100 MB snapshot pinned at 0% until the
        # moment it finished — the one thing this UI exists to prevent.
        stop = threading.Event()

        def watch() -> None:
            while not stop.is_set():
                self._set_bytes(_folder_bytes(target))
                stop.wait(0.4)

        watcher = threading.Thread(target=watch, name="hf-progress", daemon=True)
        watcher.start()
        try:
            self._hf_download(
                group.repo, list(group.allow_patterns), target, on_progress
            )
        finally:
            stop.set()
            watcher.join(timeout=2)

        done = _folder_bytes(target)
        count = _count_files(target)
        if not callback_fired:
            # The hub never reported progress (version drift): the watcher
            # still streamed live bytes, but say where the numbers came from.
            self._log(f"progress callback unavailable; counted {count} file(s)")
        with self._lock:
            self._st.current_file = ""
        self._set_bytes(done)
        if self._cancel.is_set():
            raise _Cancelled()
        self._log(f"[{group.label}] saved {count} file(s) to {target}")


# Module-level singleton — the process-wide background job.
_installer = Installer()


def snapshot() -> dict:
    return _installer.snapshot()


def start(groups: list[str]) -> dict:
    return _installer.start(groups)


def cancel() -> dict:
    return _installer.cancel()


def run_probe() -> dict:
    return _installer.run_probe()
