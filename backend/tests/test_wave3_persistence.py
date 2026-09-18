from pathlib import Path
import sqlite3

import pytest

from app.core.workflow import AssetStatus, InvalidTransition, transition
from app.persistence import Database, hash_file


def test_database_creates_wave3_tables_and_indexes(tmp_path: Path):
    database = Database(tmp_path / "studio.sqlite3")
    database.initialize()

    tables = {row[0] for row in database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    )}
    assert {"batches", "assets", "files", "jobs", "state_events", "exports"} <= tables
    assert database.schema_version() == 1


def test_source_hash_deduplicates_asset_without_overwriting_filename(tmp_path: Path):
    source = tmp_path / "same-bytes.jpg"
    source.write_bytes(b"identical source bytes")
    database = Database(tmp_path / "studio.sqlite3")
    database.initialize()

    first = database.create_asset("first.jpg", hash_file(source), "batch-1")
    duplicate = database.create_asset("renamed.jpg", hash_file(source), "batch-2")

    assert duplicate.asset_id == first.asset_id
    assert duplicate.duplicate is True
    assert database.asset_count() == 1


def test_ready_requires_approved_asset_and_verified_export(tmp_path: Path):
    database = Database(tmp_path / "studio.sqlite3")
    database.initialize()
    asset = database.create_asset("image.jpg", "hash-1", "batch-1")

    with pytest.raises(InvalidTransition):
        transition(AssetStatus.PASSED_FOR_REVIEW, AssetStatus.READY, actor="operator")

    database.transition_asset(asset.asset_id, AssetStatus.VALIDATING, "system", "intake registered")
    database.transition_asset(asset.asset_id, AssetStatus.QUEUED, "system", "queued for audit")
    database.transition_asset(asset.asset_id, AssetStatus.AUDITING, "system", "audit started")
    database.transition_asset(asset.asset_id, AssetStatus.PASSED_FOR_REVIEW, "system", "technical checks passed")
    database.transition_asset(asset.asset_id, AssetStatus.APPROVED, "operator", "approved after review")
    with pytest.raises(InvalidTransition):
        database.transition_asset(asset.asset_id, AssetStatus.READY, "operator", "not packaged")

    database.add_verified_export(asset.asset_id, "export-hash", "metadata-1")
    database.transition_asset(asset.asset_id, AssetStatus.FINALIZING, "system", "package started")
    database.transition_asset(asset.asset_id, AssetStatus.READY, "system", "package verified")
    assert database.asset_status(asset.asset_id) == AssetStatus.READY


def test_migration_refuses_newer_schema(tmp_path: Path):
    database = Database(tmp_path / "studio.sqlite3")
    database.initialize()
    database.connection.execute("UPDATE schema_meta SET version = 99")
    database.connection.commit()

    with pytest.raises(RuntimeError, match="newer"):
        database.initialize()
