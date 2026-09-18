from pathlib import Path

import pytest

from app.release import (
    BackupManifest,
    ReleaseChecklist,
    build_support_bundle,
    create_backup_manifest,
    validate_release_metadata,
)


def test_release_metadata_requires_traceable_versions():
    metadata = validate_release_metadata(
        version="0.1.0",
        source_revision="abc123",
        policy_version="wave1-baseline-2026-09",
        model_version="gemini-2.5-flash",
        prompt_version="semantic-v1",
    )
    assert metadata["version"] == "0.1.0"
    assert metadata["source_revision"] == "abc123"
    with pytest.raises(ValueError):
        validate_release_metadata(version="", source_revision="abc", policy_version="p", model_version="m", prompt_version="q")


def test_release_checklist_does_not_treat_skipped_gates_as_passed():
    checklist = ReleaseChecklist()
    checklist.record("unit", True)
    checklist.record("security", False, reason="not run", owner="owner", due_date="2026-10-01")
    assert checklist.ready is False
    assert checklist.pending_actions()[0]["gate"] == "security"


def test_backup_manifest_is_hashable_and_excludes_secrets(tmp_path: Path):
    database = tmp_path / "studio.sqlite3"
    database.write_bytes(b"database")
    manifest = create_backup_manifest(tmp_path / "backup", (database,), release_version="0.1.0")
    assert isinstance(manifest, BackupManifest)
    assert manifest.files[0]["sha256"]
    assert "api_key" not in manifest.to_dict()


def test_support_bundle_is_bounded_and_redacted(tmp_path: Path):
    bundle = build_support_bundle(
        tmp_path / "support.json",
        version="0.1.0",
        health={"provider": "configured", "api_key": "secret", "storage_root": "C:/private"},
        events=[{"code": "timeout", "message": "safe"}, {"code": "raw", "prompt": "secret prompt"}],
    )
    assert bundle.exists()
    text = bundle.read_text(encoding="utf-8")
    assert "secret" not in text
    assert "C:/private" not in text
