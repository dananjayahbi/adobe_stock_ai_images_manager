"""Verified, collision-safe ready-to-upload packaging for Wave 7."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4


@dataclass(frozen=True)
class PackageItem:
    asset_id: str
    source_hash: str
    artifact_hash: str
    normalized_path: Path
    approved_metadata_id: str
    metadata_hash: str
    policy_version: str
    approval_actor: str
    disclosure_acknowledged: bool
    verified: bool


@dataclass(frozen=True)
class PackagedItem:
    asset_id: str
    output_name: str
    output_hash: str
    metadata_id: str
    source_hash: str
    status: str = "SUCCESS"


@dataclass(frozen=True)
class ExportPackage:
    export_id: str
    batch_id: str
    items: tuple[PackagedItem, ...]
    manifest_path: Path


def _export_id(batch_id: str, items: tuple[PackageItem, ...]) -> str:
    identity = "|".join(sorted(f"{item.asset_id}:{item.artifact_hash}:{item.metadata_hash}:{item.policy_version}" for item in items))
    return hashlib.sha256(f"{batch_id}|{identity}".encode()).hexdigest()[:20]


def _safe_name(item: PackageItem) -> str:
    return f"{item.asset_id[:12]}-{item.metadata_hash[:12]}.jpg"


def package_ready(output_dir: Path, batch_id: str, items: tuple[PackageItem, ...]) -> ExportPackage:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    export_id = _export_id(batch_id, items)
    manifest_path = output_dir / f"manifest-{export_id}.json"
    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ExportPackage(export_id, batch_id, tuple(PackagedItem(**entry) for entry in raw["items"]), manifest_path)

    packaged: list[PackagedItem] = []
    temporary: list[Path] = []
    try:
        for item in items:
            if not item.approval_actor.strip():
                raise ValueError("approval actor is required")
            if not item.verified:
                raise ValueError("item is not verified")
            if not item.disclosure_acknowledged:
                raise ValueError("disclosure acknowledgment is required")
            if not item.normalized_path.is_file():
                raise ValueError("normalized artifact is unavailable")
            name = _safe_name(item)
            target = output_dir / name
            if target.exists():
                raise ValueError("output collision requires a new export identity")
            temporary_path = output_dir / f".{export_id}-{uuid4().hex}.tmp"
            shutil.copyfile(item.normalized_path, temporary_path)
            temporary.append(temporary_path)
            digest = hashlib.sha256(temporary_path.read_bytes()).hexdigest()
            temporary_path.replace(target)
            temporary.remove(temporary_path)
            packaged.append(PackagedItem(item.asset_id, name, digest, item.approved_metadata_id, item.source_hash))
        manifest = {
            "export_id": export_id,
            "batch_id": batch_id,
            "disclosure_reminder": "Complete Adobe generative-AI disclosure in the contributor portal.",
            "items": [asdict(entry) for entry in packaged],
        }
        temporary_manifest = output_dir / f".{manifest_path.name}.tmp"
        temporary_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        temporary_manifest.replace(manifest_path)
        return ExportPackage(export_id, batch_id, tuple(packaged), manifest_path)
    except Exception:
        for path in temporary:
            path.unlink(missing_ok=True)
        raise
