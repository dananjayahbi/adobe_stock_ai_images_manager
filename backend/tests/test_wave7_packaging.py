from pathlib import Path

import pytest

from app.metadata import MetadataStore, MetadataStatus, MetadataSource
from app.packaging import ExportPackage, PackageItem, package_ready


def test_metadata_versions_are_immutable_and_approval_is_current(tmp_path: Path):
    store = MetadataStore(tmp_path / "metadata.jsonl")
    first = store.create(
        asset_id="asset-1",
        artifact_hash="a" * 64,
        title="A garden",
        keywords=("garden", "green"),
        source=MetadataSource.PROVIDER_GENERATED,
        policy_version="policy-1",
        valid=True,
    )
    approved = store.approve(first.version_id, actor="operator", reason="reviewed")
    edited = store.edit(approved.version_id, title="A bright garden", actor="operator", reason="correction")

    assert first.status is MetadataStatus.PROPOSED
    assert approved.status is MetadataStatus.APPROVED
    assert edited.status is MetadataStatus.PROPOSED
    assert store.current_approved("asset-1") is None
    assert store.get(first.version_id).title == "A garden"


def test_ready_package_is_verified_collision_safe_and_idempotent(tmp_path: Path):
    normalized = tmp_path / "normalized.jpg"
    normalized.write_bytes(b"jpeg-bytes")
    output = tmp_path / "ready"
    output.mkdir()

    item = PackageItem(
        asset_id="asset-1",
        source_hash="s" * 64,
        artifact_hash="a" * 64,
        normalized_path=normalized,
        approved_metadata_id="metadata-1",
        metadata_hash="m" * 64,
        policy_version="policy-1",
        approval_actor="operator",
        disclosure_acknowledged=True,
        verified=True,
    )
    first = package_ready(output, "batch-1", (item,))
    second = package_ready(output, "batch-1", (item,))

    assert isinstance(first, ExportPackage)
    assert first.export_id == second.export_id
    assert first.items[0].output_name == second.items[0].output_name
    assert (output / first.items[0].output_name).read_bytes() == b"jpeg-bytes"
    assert first.manifest_path.exists()


def test_package_rejects_unverified_or_missing_disclosure(tmp_path: Path):
    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg")
    item = PackageItem(
        asset_id="asset-1", source_hash="s", artifact_hash="a", normalized_path=image,
        approved_metadata_id="m", metadata_hash="h", policy_version="p", approval_actor="operator",
        disclosure_acknowledged=False, verified=True,
    )

    with pytest.raises(ValueError, match="disclosure"):
        package_ready(tmp_path / "ready", "batch", (item,))
