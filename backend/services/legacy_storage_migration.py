"""One-time migration of legacy Adobe Stock storage into the platform layout.

Before the universal multi-platform system, everything lived directly under
``<repo>/storage`` (``inbox/``, ``thumbnails/``, ..., ``adobe_stock.db``).
The new layout gives every platform a dedicated root:

``storage/platforms/adobe_stock/{inbox, thumbnails, ..., adobe_stock.db}``

:func:`migrate_legacy_storage` moves the legacy directories and the SQLite
database (plus its ``-shm``/``-wal`` sidecars) into that root and then rewrites
the absolute path prefixes stored *inside* the database, because records hold
full file paths (``...\\storage\\inbox\\x.jpg``) that would otherwise point at
the now-empty legacy locations.

Safety rules baked into the design:

* **Marker-gated**: a ``.migrated`` marker inside the platform root makes the
  migration a no-op on every later start. The marker is written only when the
  run had zero failures; a failed run therefore retries on the next start.
* **Never overwrites, never deletes data**: if a destination already exists
  (likely created empty by ``create_data_directories()`` at main.py import
  time, *before* migration runs), the legacy dir's children are moved one by
  one and any child whose name already exists at the destination is skipped
  with a warning.
* **``app_settings.json`` stays at the storage root** — it is app-level,
  operator-owned configuration shared across platforms, not Adobe platform
  data, so it is deliberately absent from the legacy item list and must never
  be moved.

:func:`run_legacy_storage_migration` is the thin wrapper ``main.py`` calls as
the FIRST lifespan action: it logs the outcome and swallows unexpected errors
so a migration problem can never take the app down (data must never be lost
because migration failed).
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

#: Legacy data directories directly under storage_root, in the canonical
#: order used by platforms.paths.STANDARD_SUBDIRS (readability order first).
LEGACY_SUBDIRS: tuple[str, ...] = (
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

#: SQLite always ships three files in WAL mode: the DB plus its shared-memory
#: and write-ahead sidecars. They must travel together or the next open would
#: silently roll back recent commits.
_DB_SIDECAR_SUFFIXES: tuple[str, ...] = ("-shm", "-wal")


def _move_item(src: Path, dst: Path) -> tuple[bool, int, int]:
    """Move one legacy item, returning ``(failed, moved, skipped)`` counts.

    Directories move wholesale when the destination does not exist. When the
    destination DOES exist (``create_data_directories()`` may have pre-created
    empty platform subdirs before this runs), each child is moved
    individually; a child already present at the destination is skipped with
    a warning — never overwritten. Never raises for per-child problems: a
    failure is reported via the ``failed`` flag and logged.
    """
    moved = skipped = 0
    if not dst.exists():
        try:
            shutil.move(str(src), str(dst))
            return False, 1, 0
        except OSError as exc:
            logger.warning("Could not move %s -> %s: %s", src, dst, exc)
            return True, 0, 0
    # Destination exists: merge children instead of overwriting it.
    if not src.is_dir() or not dst.is_dir():
        logger.warning(
            "Cannot merge %s into %s (not both directories); skipping", src, dst
        )
        return True, 0, 0
    had_failure = False
    for child in sorted(src.iterdir()):
        target = dst / child.name
        if target.exists():
            logger.warning(
                "Skipping %s: destination %s already exists", child, target
            )
            skipped += 1
            continue
        try:
            shutil.move(str(child), str(target))
            moved += 1
        except OSError as exc:
            # Keep going: one bad child must not strand the remaining ones.
            logger.warning("Could not move %s -> %s: %s", child, target, exc)
            had_failure = True
    return had_failure, moved, skipped


def _rewrite_db_path_prefixes(
    db_path: Path, storage_root: Path, platform_root: Path
) -> None:
    """Rewrite stored absolute path prefixes inside the migrated database.

    Records store full file paths (``E:\\...\\storage\\inbox\\x.jpg``); after
    the move those files live under ``platform_root``. Every TEXT-ish column
    of every table is updated with parameterized ``REPLACE`` calls for both
    separator spellings (Windows ``\\`` and POSIX ``/``), so the records keep
    pointing at their moved files.
    """
    prefix_pairs = [
        (str(storage_root) + os.sep, str(platform_root) + os.sep),
        (storage_root.as_posix() + "/", platform_root.as_posix() + "/"),
    ]
    # ``with sqlite3.connect(...)`` commits/rolls back but does NOT close the
    # connection; close explicitly so no handle leaks past this function.
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        for table in tables:
            quoted_table = '"' + table.replace('"', '""') + '"'
            columns = conn.execute(
                f"PRAGMA table_info({quoted_table})"
            ).fetchall()
            text_cols = [
                col[1]
                for col in columns
                if any(
                    token in (col[2] or "").upper()
                    for token in ("TEXT", "VARCHAR", "CHAR")
                )
            ]
            for col in text_cols:
                quoted_col = '"' + col.replace('"', '""') + '"'
                for old, new in prefix_pairs:
                    conn.execute(
                        f'UPDATE {quoted_table} SET {quoted_col} = '
                        f"REPLACE({quoted_col}, :old, :new)",
                        {"old": old, "new": new},
                    )
        conn.commit()
    finally:
        conn.close()


def migrate_legacy_storage(
    storage_root: Path,
    platform_root: Path | None = None,
    db_filename: str = "adobe_stock.db",
    marker_name: str = ".migrated",
) -> str:
    """Move legacy Adobe Stock data into ``platform_root`` (one time).

    Returns a short status message (``"already migrated"`` when the marker
    exists). Failures are logged and reported in the message; the marker is
    only written when there were none, so the next start retries.
    """
    storage_root = Path(storage_root)
    if platform_root is None:
        platform_root = storage_root / "platforms" / "adobe_stock"
    platform_root = Path(platform_root)

    marker = platform_root / marker_name
    if marker.exists():
        return "already migrated"

    platform_root.mkdir(parents=True, exist_ok=True)

    moved = skipped = 0
    failures: list[str] = []

    # Data directories first, then the database trio (the path-prefix rewrite
    # needs the DB at its final location to run).
    for name in LEGACY_SUBDIRS:
        src = storage_root / name
        if not src.exists():
            continue
        failed, n_moved, n_skipped = _move_item(src, platform_root / name)
        moved += n_moved
        skipped += n_skipped
        if failed:
            failures.append(name)

    for name in (db_filename, *(db_filename + s for s in _DB_SIDECAR_SUFFIXES)):
        src = storage_root / name
        if not src.exists():
            continue
        dst = platform_root / name
        if dst.exists():
            # Never overwrite a DB that already lives at the destination.
            logger.warning("Skipping %s: destination %s already exists", src, dst)
            skipped += 1
            # PRODUCT BUG FIX: the legacy DB never arrived at its new home, so
            # count this as a failure — otherwise the marker is stamped, every
            # later start returns "already migrated", and the un-migrated
            # legacy DB is orphaned silently forever. Withholding the marker
            # keeps the conflict reported on each start until resolved.
            failures.append(name)
            continue
        try:
            shutil.move(str(src), str(dst))
            moved += 1
        except OSError as exc:
            logger.warning("Could not move %s -> %s: %s", src, dst, exc)
            failures.append(name)

    # Point every stored record at its moved file — only relevant once the DB
    # itself sits at its new home (if its move failed, the failure is already
    # tracked above and no rewrite can be done for a DB that never arrived).
    migrated_db = platform_root / db_filename
    if migrated_db.exists():
        try:
            _rewrite_db_path_prefixes(migrated_db, storage_root, platform_root)
        except Exception as exc:  # noqa: BLE001 — any rewrite error = retry later
            logger.warning("Path-prefix rewrite failed for %s: %s", migrated_db, exc)
            failures.append(db_filename)

    if failures:
        return (
            f"migration incomplete: {len(failures)} failure(s) "
            f"({', '.join(failures)}); migrated {moved} item(s), "
            f"skipped {skipped}"
        )

    # Success: stamp the marker (with a timestamp) so later starts no-op.
    marker.write_text(
        datetime.now(timezone.utc).isoformat(timespec="seconds")
        + f" migrated {moved} item(s), skipped {skipped}\n",
        encoding="utf-8",
    )
    if moved == 0 and skipped == 0:
        return "nothing to migrate"
    return f"migrated {moved} item(s), skipped {skipped}"


def run_legacy_storage_migration() -> None:
    """Lifespan entry point: migrate config's STORAGE_ROOT, never crash.

    Imported by ``main.py`` as the FIRST lifespan action (before
    ``create_data_directories`` creates the destination skeleton and before
    ``Base.metadata.create_all`` opens the new DB path). Any unexpected
    top-level error is logged, not raised: a broken migration must not stop
    the app from starting, and the absent marker guarantees a retry next
    start.
    """
    from config import STORAGE_ROOT  # local import: avoids import-time cycles

    try:
        message = migrate_legacy_storage(STORAGE_ROOT)
        logger.info("Legacy storage migration: %s", message)
    except Exception:  # noqa: BLE001 — startup must survive any migration bug
        logger.exception(
            "Legacy storage migration failed unexpectedly; will retry next start"
        )
