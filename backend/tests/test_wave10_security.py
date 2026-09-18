from pathlib import Path

from app.core.storage import StorageLayout
from app.release import build_support_bundle


def test_support_bundle_limits_event_count_and_does_not_include_raw_payload(tmp_path: Path):
    path = build_support_bundle(
        tmp_path / "bundle.json",
        version="0.1.0",
        health={"database": "ok"},
        events=[{"code": "safe", "raw_payload": "do-not-export"}] * 100,
        max_events=3,
    )
    text = path.read_text(encoding="utf-8")
    assert text.count('"code"') == 3
    assert "raw_payload" not in text


def test_managed_storage_rejects_paths_outside_root(tmp_path: Path):
    layout = StorageLayout(tmp_path / "storage")
    layout.ensure_exists()
    assert layout.contains(layout.inbox / "asset.source")
    assert not layout.contains(tmp_path / "outside.txt")
