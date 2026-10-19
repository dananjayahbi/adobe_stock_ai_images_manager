"""Unit tests for services.legacy_storage_migration — pure tmp_path only.

Builds a complete fake legacy layout (10 legacy dirs, real files, a sqlite DB
with backslash *and* forward-slash path rows, app_settings.json at the root)
and exercises the three safety contracts:

* A: happy path — merge into pre-created empty target dirs, DB move,
  path-prefix rewrite for both slash styles, app_settings.json stays put,
  marker stamped.
* B: idempotence — second run is a no-op ("already migrated"), marker bytes
  and mtime untouched.
* C: never-clobber — a pre-existing NON-EMPTY destination DB is not
  overwritten, no data is lost, and the unresolved conflict withholds the
  marker so every later start keeps reporting it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from services.legacy_storage_migration import (
    LEGACY_SUBDIRS,
    migrate_legacy_storage,
)

APP_SETTINGS_CONTENTS = '{"theme": "dark", "endpoint": "http://localhost:11434"}'


def _build_legacy_storage(tmp_path: Path) -> Path:
    """Create the pre-platform layout under ``tmp_path/storage``."""
    storage = tmp_path / "storage"
    for name in LEGACY_SUBDIRS:
        (storage / name).mkdir(parents=True)

    (storage / "inbox" / "a.jpg").write_bytes(b"\xff\xd8\xff\xea legacy-a")
    (storage / "inbox" / "b.jpg").write_bytes(b"\xff\xd8\xff\xea legacy-b")
    (storage / "thumbnails" / "a.jpg").write_bytes(b"\xff\xd8\xff\xea thumb-a")
    (storage / "thumbnails" / "b.jpg").write_bytes(b"\xff\xd8\xff\xea thumb-b")

    conn = sqlite3.connect(storage / "adobe_stock.db")
    try:
        conn.execute(
            "CREATE TABLE records ("
            "id INTEGER PRIMARY KEY, "
            "original_path TEXT, "
            "thumbnail_path TEXT)"
        )
        rows = [
            # Windows backslash spellings.
            (
                1,
                str(storage / "inbox" / "a.jpg"),
                str(storage / "thumbnails" / "a.jpg"),
            ),
            # POSIX / spellings (as_posix style).
            (
                2,
                (storage / "inbox" / "b.jpg").as_posix(),
                (storage / "thumbnails" / "b.jpg").as_posix(),
            ),
        ]
        conn.executemany(
            "INSERT INTO records (id, original_path, thumbnail_path) "
            "VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    (storage / "app_settings.json").write_text(
        APP_SETTINGS_CONTENTS, encoding="utf-8"
    )
    return storage


def _read_records(db_path: Path) -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT id, original_path, thumbnail_path FROM records ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _make_destination_db(db_path: Path, note: str) -> None:
    """Create a NON-EMPTY database at the migration destination."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE existing (id INTEGER PRIMARY KEY, note TEXT)")
        conn.execute("INSERT INTO existing (note) VALUES (?)", (note,))
        conn.commit()
    finally:
        conn.close()


def test_happy_path_merges_moves_rewrites_and_stamps_marker(tmp_path):
    """Files + DB land under platforms/adobe_stock; both slash styles fixed."""
    assert len(LEGACY_SUBDIRS) == 10
    storage = _build_legacy_storage(tmp_path)
    platform_root = storage / "platforms" / "adobe_stock"

    # Pre-create 2 empty target dirs to exercise the merge-children path
    # (mirrors create_data_directories() running before the migration).
    (platform_root / "inbox").mkdir(parents=True)
    (platform_root / "thumbnails").mkdir(parents=True)

    message = migrate_legacy_storage(storage)
    assert message.startswith("migrated "), message
    assert "skipped 0" in message, message
    assert "failure" not in message, message

    # Every legacy dir now exists under the platform root.
    for name in LEGACY_SUBDIRS:
        assert (platform_root / name).is_dir(), name
    assert (platform_root / "inbox" / "a.jpg").is_file()
    assert (platform_root / "inbox" / "b.jpg").is_file()
    assert (platform_root / "thumbnails" / "a.jpg").is_file()
    assert (platform_root / "thumbnails" / "b.jpg").is_file()

    # Pre-created dirs merged (legacy source left behind but empty);
    # wholesale-moved dirs are gone from the legacy root entirely.
    for name in LEGACY_SUBDIRS:
        legacy = storage / name
        if legacy.exists():
            assert not any(legacy.iterdir()), name

    # DB moved; sidecar-free legacy file no longer at the old location.
    assert (platform_root / "adobe_stock.db").is_file()
    assert not (storage / "adobe_stock.db").exists()

    # Rows rewritten to the NEW prefix in both separator spellings.
    backslash_original = str(platform_root / "inbox" / "a.jpg")
    backslash_thumb = str(platform_root / "thumbnails" / "a.jpg")
    posix_original = (platform_root / "inbox" / "b.jpg").as_posix()
    posix_thumb = (platform_root / "thumbnails" / "b.jpg").as_posix()
    records = _read_records(platform_root / "adobe_stock.db")
    assert records == [
        (1, backslash_original, backslash_thumb),
        (2, posix_original, posix_thumb),
    ]
    # The rewritten rows actually point at files that exist.
    assert Path(backslash_original).is_file()
    assert Path(posix_original).is_file()

    # app_settings.json stays at the storage root — never platform data.
    assert (storage / "app_settings.json").read_text(encoding="utf-8") == (
        APP_SETTINGS_CONTENTS
    )
    assert not (platform_root / "app_settings.json").exists()

    # Marker written on a clean run.
    marker = platform_root / ".migrated"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip()


def test_second_run_is_noop_and_marker_untouched(tmp_path):
    """After a successful run the marker gates everything to a no-op."""
    storage = _build_legacy_storage(tmp_path)
    first = migrate_legacy_storage(storage)
    assert first.startswith("migrated "), first

    platform_root = storage / "platforms" / "adobe_stock"
    marker = platform_root / ".migrated"
    assert marker.is_file()
    marker_bytes = marker.read_bytes()
    marker_mtime = marker.stat().st_mtime_ns
    snapshot = sorted(
        p.relative_to(platform_root).as_posix()
        for p in platform_root.rglob("*")
    )

    second = migrate_legacy_storage(storage)
    assert second == "already migrated"

    assert marker.read_bytes() == marker_bytes
    assert marker.stat().st_mtime_ns == marker_mtime
    assert sorted(
        p.relative_to(platform_root).as_posix()
        for p in platform_root.rglob("*")
    ) == snapshot
    # Legacy locations still hold no stray data after the no-op run:
    # every legacy dir and the DB were wholesale-moved in run 1.
    assert not (storage / "adobe_stock.db").exists()
    for name in LEGACY_SUBDIRS:
        assert not (storage / name).exists(), name


def test_existing_destination_db_is_never_overwritten(tmp_path):
    """A non-empty destination DB wins; the conflict withholds the marker.

    The legacy DB must survive untouched (never clobbered, never deleted),
    the destination DB keeps its data, and because the migration did NOT
    complete, no ``.migrated`` marker is stamped — the next start retries and
    reports the conflict again instead of silently declaring success.
    """
    storage = _build_legacy_storage(tmp_path)
    platform_root = storage / "platforms" / "adobe_stock"
    dest_db = platform_root / "adobe_stock.db"
    _make_destination_db(dest_db, "destination-data")
    dest_bytes_before = dest_db.read_bytes()

    legacy_db = storage / "adobe_stock.db"
    legacy_bytes_before = legacy_db.read_bytes()
    assert legacy_bytes_before != dest_bytes_before

    message = migrate_legacy_storage(storage)

    # Conflict reported as an incomplete migration, naming the DB.
    assert message.startswith("migration incomplete"), message
    assert "adobe_stock.db" in message, message
    # Destination DB never overwritten; its data intact.
    assert dest_db.read_bytes() == dest_bytes_before
    conn = sqlite3.connect(dest_db)
    try:
        notes = conn.execute("SELECT note FROM existing").fetchall()
    finally:
        conn.close()
    assert notes == [("destination-data",)]
    # Legacy DB still at the legacy location with identical bytes — no loss.
    assert legacy_db.is_file()
    assert legacy_db.read_bytes() == legacy_bytes_before
    # No data directories were harmed either.
    assert (platform_root / "inbox" / "a.jpg").is_file()
    # Marker NOT written: a skipped DB move counts as a failure.
    assert not (platform_root / ".migrated").exists()

    # A second start retries and keeps surfacing the same conflict.
    retry = migrate_legacy_storage(storage)
    assert retry.startswith("migration incomplete"), retry
    assert "adobe_stock.db" in retry, retry
    assert legacy_db.read_bytes() == legacy_bytes_before
    assert dest_db.read_bytes() == dest_bytes_before
    assert not (platform_root / ".migrated").exists()
