"""Workspace-local homes for every downloaded model weight.

The whole point of this module is **shareability**: copy ``<repo>/models`` to
another machine and that machine has every weight this app needs, with no
home-directory state to chase down. Nothing lives under ``~`` any more.

rembg resolves its model home in this order::

    U2NET_HOME  ->  REMBG_HOME  ->  ~/.rembg

so both of the first two are pointed at the same directory. That makes every
rembg path — ``<home>/models/<name>/<name>.onnx`` for the modern layout and
``<home>/<name>.onnx`` for the legacy one — land inside the workspace, and it
means a checkout that already has weights in either layout just works.

The Hugging Face cache (``HF_HOME``) is relocated the same way; it is where the
ViTMatte weights live once the matting stack is installed.

Environment variables are only *defaulted*: an explicit ``U2NET_HOME`` in the
shell still wins, so a machine with weights elsewhere is not overridden.

Use as a module (``apply_env()`` is called from ``config.py`` before anything
imports rembg or transformers) or as a one-off migrator::

    .venv/Scripts/python -m services.model_paths
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

#: ``backend/services/model_paths.py`` -> parents[2] == ``<repo>``.
#: Deliberately recomputed rather than imported from ``config``: this module is
#: imported *by* config.py, and the dependency must not run the other way.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Everything this app downloads, and the only directory a user ever copies.
MODELS_DIR = REPO_ROOT / "models"

#: rembg home — ``U2NET_HOME`` and ``REMBG_HOME`` both point here.
REMBG_DIR = MODELS_DIR / "rembg"

#: Hugging Face cache — ``HF_HOME`` points here.
HF_DIR = MODELS_DIR / "huggingface"

#: True once the environment variables have been written this process.
_applied = False


def apply_env() -> Path:
    """Point every model cache at the workspace and ensure the folders exist.

    Idempotent, and safe to call at import time: a later explicit value in the
    environment is never overwritten. Returns the rembg home.
    """
    global _applied
    if _applied:
        return REMBG_DIR

    REMBG_DIR.mkdir(parents=True, exist_ok=True)
    HF_DIR.mkdir(parents=True, exist_ok=True)

    # setdefault, not assignment — an operator who exported U2NET_HOME keeps it.
    os.environ.setdefault("U2NET_HOME", str(REMBG_DIR))
    os.environ.setdefault("REMBG_HOME", str(REMBG_DIR))
    os.environ.setdefault("HF_HOME", str(HF_DIR))

    _applied = True
    return REMBG_DIR


def _move_children(source: Path, target: Path) -> list[str]:
    """Move each child of ``source`` into ``target``, skipping name clashes.

    A clash means the workspace copy already exists, so the local one is left
    alone — migration is a one-way, never-destructive move.
    """
    moved: list[str] = []
    if not source.is_dir():
        return moved

    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir()):
        destination = target / child.name
        if destination.exists():
            continue
        shutil.move(str(child), str(destination))
        moved.append(f"{child} -> {destination}")
    return moved


def migrate_legacy_caches() -> list[str]:
    """Relocate weights already downloaded outside the repo (0 bytes moved on the wire).

    Two historical layouts are folded into ``<repo>/models``:

    * ``~/.rembg/**``  -> ``models/rembg/**`` (keeps the ``models/<name>/`` tree)
    * ``~/.u2net/*.onnx`` -> ``models/rembg/`` (rembg's legacy home root)
    * ``~/.cache/huggingface/**`` -> ``models/huggingface/**``

    Returns a line per file moved; empty when there was nothing to do.
    """
    apply_env()
    home = Path.home()
    notes: list[str] = []
    notes += _move_children(home / ".rembg", REMBG_DIR)
    notes += _move_children(home / ".u2net", REMBG_DIR)
    notes += _move_children(home / ".cache" / "huggingface", HF_DIR)
    return notes


def describe() -> dict:
    """Where the weights live and how big each home is — for the config page."""
    def folder_size(path: Path) -> int:
        if not path.is_dir():
            return 0
        return sum(
            f.stat().st_size
            for f in path.rglob("*")
            if f.is_file()
        )

    return {
        "models_dir": str(MODELS_DIR),
        "rembg_dir": str(REMBG_DIR),
        "hf_dir": str(HF_DIR),
        "rembg_bytes": folder_size(REMBG_DIR),
        "hf_bytes": folder_size(HF_DIR),
        "env": {
            "U2NET_HOME": os.environ.get("U2NET_HOME", ""),
            "REMBG_HOME": os.environ.get("REMBG_HOME", ""),
            "HF_HOME": os.environ.get("HF_HOME", ""),
        },
    }


if __name__ == "__main__":  # pragma: no cover - manual operator tool
    print(f"models -> {MODELS_DIR}")
    for line in migrate_legacy_caches():
        print(f"moved  {line}")
    if not any((Path.home() / d).is_dir() for d in (".rembg", ".u2net")):
        print("nothing to migrate")
    print(f"rembg home : {describe()['rembg_bytes'] / 1e6:.1f} MB")
    print(f"hf home    : {describe()['hf_bytes'] / 1e6:.1f} MB")
