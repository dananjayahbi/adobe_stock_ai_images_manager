"""Per-platform storage paths — the data-isolation contract.

Future platform adapters MUST resolve their directories and database through
:func:`get_platform_paths` instead of the global ``settings.INBOX_DIR`` and
friends. The ``settings.*_DIR`` fields point at the Adobe Stock platform root
for legacy compatibility (dozens of existing services read them), so they are
Adobe-only by construction; a new platform reading them would silently leak
Adobe data into its own pipeline.

Layout::

    storage/
        app_settings.json        # app-level, shared — never platform data
        platforms/
            adobe_stock/
                inbox/ thumbnails/ ready_to_upload/ refined/ upscaled/
                converted/ removed/ white/ srgb/ quarantine/
                adobe_stock.db
            <platform_id>/
                ... same subdirectories, own <platform_id>.db
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import ADOBE_STOCK_ROOT, PLATFORMS_ROOT

#: Every platform owns the same subdirectory skeleton; their names mirror the
#: Settings field names (inbox -> INBOX_DIR, ready_to_upload -> READY_DIR, ...)
#: so a platform adapter can translate 1:1 from the legacy Adobe code paths.
STANDARD_SUBDIRS: tuple[str, ...] = (
    "inbox",
    "thumbnails",
    "ready_to_upload",
    "refined",
    "upscaled",
    "converted",
    "removed",
    "white",
    "srgb",
    "quarantine",
)


@dataclass(frozen=True)
class PlatformPaths:
    """Filesystem locations for one platform.

    Field names mirror the ``Settings`` dir fields (``inbox_dir``,
    ``ready_dir``, ...) so refactors from ``settings.X`` to
    ``paths.X`` are mechanical.
    """

    root: Path
    inbox_dir: Path
    thumbnails_dir: Path
    ready_dir: Path
    refined_dir: Path
    upscaled_dir: Path
    converted_dir: Path
    removed_dir: Path
    white_dir: Path
    srgb_dir: Path
    quarantine_dir: Path
    db_path: Path


def platform_root(platform_id: str) -> Path:
    """Return ``storage/platforms/<platform_id>`` (not created)."""
    return PLATFORMS_ROOT / platform_id


def platform_db_path(platform_id: str) -> Path:
    """Return the platform's dedicated SQLite file path (not created)."""
    return platform_root(platform_id) / f"{platform_id}.db"


def get_platform_paths(platform_id: str, create: bool = True) -> PlatformPaths:
    """Build the :class:`PlatformPaths` for ``platform_id``.

    When ``create`` is true (the default), every standard subdirectory is
    created (``parents=True, exist_ok=True``) so callers — routers, tasks,
    adapters — can write immediately without a separate mkdir pass. Pass
    ``create=False`` for read-only probing where touching the filesystem
    would be a side effect (e.g. tests asserting layout).
    """
    root = platform_root(platform_id)
    if platform_id == "adobe_stock":
        # Tie Adobe's root straight to config so this contract and the legacy
        # settings.*_DIR fields can never drift apart (they are equal by
        # construction; the explicit reference documents the intent).
        root = ADOBE_STOCK_ROOT
    subdir = {name: root / name for name in STANDARD_SUBDIRS}
    if create:
        for path in subdir.values():
            path.mkdir(parents=True, exist_ok=True)
    return PlatformPaths(
        root=root,
        inbox_dir=subdir["inbox"],
        thumbnails_dir=subdir["thumbnails"],
        ready_dir=subdir["ready_to_upload"],
        refined_dir=subdir["refined"],
        upscaled_dir=subdir["upscaled"],
        converted_dir=subdir["converted"],
        removed_dir=subdir["removed"],
        white_dir=subdir["white"],
        srgb_dir=subdir["srgb"],
        quarantine_dir=subdir["quarantine"],
        db_path=platform_db_path(platform_id),
    )
