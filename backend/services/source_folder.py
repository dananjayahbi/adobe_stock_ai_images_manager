"""Source-folder resolution for the browse/import APIs.

Everything that touches the operator's source folder goes through this module
so the containment rule lives in exactly one place:

* ``routers/fs.py``        - browse and thumbnail endpoints
* ``routers/batches.py``   - ``POST /api/batches`` with ``files: [rel, ...]``

The contract for a relative path ``rel``:

1. A source folder must be configured (else ``400``).
2. ``realpath(root / rel)`` must stay inside ``realpath(root)`` (else ``403``)
   — ``..`` segments and symlinks resolving outside the root are escapes.
3. Whatever the path *is* (missing, a directory, a non-image) is the caller's
   concern: this module reports existence separately so each endpoint can pick
   its own ``404``/``400`` detail.

``Path.resolve()``/``os.path.realpath`` normalise ``..`` lexically for
non-existent tails too, so an escape is caught before the file is ever opened.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import HTTPException

from services import app_settings

#: Extensions the browser lists and the thumbnail endpoint will serve. The
#: import path is stricter (``config.Settings.ALLOWED_EXTENSIONS``); browsing
#: stays liberal so the operator can *see* what is in the folder even when a
#: file cannot be imported into a batch.
IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
)

_UNCONFIGURED = "No source folder configured. Set one in Settings first."


def configured_path() -> str:
    """The stored source folder, trimmed; ``""`` when unset or cleared."""
    return str(app_settings.load_raw().get("source_folder") or "").strip()


def require_root() -> Path:
    """The configured source folder; ``400`` when there is none."""
    raw = configured_path()
    if not raw:
        raise HTTPException(status_code=400, detail=_UNCONFIGURED)
    return Path(raw)


def resolve_inside(rel: str) -> Path:
    """Realpath of ``rel`` under the source root.

    Raises ``400`` when no folder is configured and ``403`` when the resolved
    path escapes the root. Missing files are returned as-is — existence is
    checked by the caller (an escape must be refused even when the file does
    not exist yet).
    """
    root_real = Path(os.path.realpath(require_root()))
    # os.path.join drops the root when rel carries its own drive/anchor, so a
    # "C:\\evil" or "/etc" style value resolves absolutely and then fails the
    # containment check below instead of being silently rooted.
    candidate = Path(os.path.realpath(os.path.join(str(root_real), rel or "")))
    if candidate != root_real and root_real not in candidate.parents:
        raise HTTPException(
            status_code=403,
            detail=f"Path escapes the source folder: {rel}",
        )
    return candidate


def resolve_dir(rel: str) -> Path:
    """A contained directory; ``404`` when missing, ``400`` when not a dir."""
    target = resolve_inside(rel)
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Not found: {rel}")
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {rel}")
    return target


def resolve_image_file(rel: str) -> Path:
    """A contained, existing image file.

    Guards in order: containment (``403``), extension (``400`` — a non-image
    is never served even if it exists), existence (``404``).
    """
    target = resolve_inside(rel)
    if target.suffix.lower() not in IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Not a supported image extension: {rel}",
        )
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Not found: {rel}")
    return target


def relative_parts(rel: str) -> list[str]:
    """Breadcrumb segments of ``rel`` under the root (``"a/b" -> ["a", "b"]``).

    Both separators are accepted so a Windows client may send either form;
    empty and ``.`` pieces drop out so ``""`` and ``"/a/"`` normalise cleanly.
    """
    return [
        part
        for part in re.split(r"[\\/]+", rel or "")
        if part and part != "."
    ]


def parent_rel(parts: list[str]) -> str | None:
    """The parent directory's relative path, or ``None`` at the root."""
    if not parts:
        return None
    return "/".join(parts[:-1])
