"""Release evidence, safe support bundles, and backup manifests for Wave 10."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any, Iterable, Mapping


_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def validate_release_metadata(*, version: str, source_revision: str, policy_version: str, model_version: str, prompt_version: str) -> dict[str, str]:
    values = {"version": version, "source_revision": source_revision, "policy_version": policy_version, "model_version": model_version, "prompt_version": prompt_version}
    if not _VERSION.fullmatch(version) or any(not value.strip() for value in values.values()):
        raise ValueError("release metadata requires a semantic version and non-empty provenance")
    return values


@dataclass
class ReleaseChecklist:
    gates: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, gate: str, passed: bool, *, reason: str | None = None, owner: str | None = None, due_date: str | None = None) -> None:
        if not gate.strip():
            raise ValueError("gate is required")
        if not passed and not all((reason, owner, due_date)):
            raise ValueError("skipped or failed gates require reason, owner, and due date")
        self.gates[gate] = {"passed": passed, "reason": reason, "owner": owner, "due_date": due_date}

    @property
    def ready(self) -> bool:
        return bool(self.gates) and all(entry["passed"] for entry in self.gates.values())

    def pending_actions(self) -> list[dict[str, Any]]:
        return [{"gate": gate, **entry} for gate, entry in self.gates.items() if not entry["passed"]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class BackupManifest:
    root: Path
    release_version: str
    created_at: str
    files: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {"release_version": self.release_version, "created_at": self.created_at, "files": list(self.files)}


def create_backup_manifest(destination: Path, paths: Iterable[Path], *, release_version: str) -> BackupManifest:
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for source in paths:
        source = Path(source)
        if not source.is_file():
            raise ValueError(f"backup source is not a file: {source.name}")
        target = destination / source.name
        if target.resolve() != source.resolve():
            shutil.copy2(source, target)
        entries.append({"name": source.name, "sha256": _sha256(target), "bytes": str(target.stat().st_size)})
    manifest = BackupManifest(destination, release_version, datetime.now(timezone.utc).isoformat(), tuple(entries))
    (destination / "manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def build_support_bundle(path: Path, *, version: str, health: Mapping[str, Any], events: Iterable[Mapping[str, Any]], max_events: int = 50) -> Path:
    def safe_health() -> dict[str, Any]:
        allowed = {"provider", "database", "storage", "queue", "migration", "tools", "version"}
        return {key: value for key, value in health.items() if key in allowed and not any(secret in key.lower() for secret in ("key", "token", "secret", "password"))}

    safe_events = []
    for event in list(events)[:max_events]:
        safe_events.append({key: str(value)[:300] for key, value in event.items() if key in {"code", "stage", "outcome", "duration", "correlation_id"}})
    payload = {"version": version, "created_at": datetime.now(timezone.utc).isoformat(), "health": safe_health(), "events": safe_events}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
