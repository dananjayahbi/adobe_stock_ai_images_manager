"""Immutable metadata proposals and approvals for Wave 7."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from app.core.policy import PolicyBaseline, validate_metadata


class MetadataSource(str, Enum):
    PROVIDER_GENERATED = "provider-generated"
    USER_EDITED = "user-edited"
    IMPORTED = "imported"
    APPROVED = "approved"


class MetadataStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class MetadataVersion:
    version_id: str
    asset_id: str
    artifact_hash: str
    title: str
    keywords: tuple[str, ...]
    language: str
    source: MetadataSource
    status: MetadataStatus
    policy_version: str
    valid: bool
    parent_version_id: str | None = None
    actor: str | None = None
    reason: str | None = None

    @property
    def content_hash(self) -> str:
        value = json.dumps(
            {"title": self.title, "keywords": self.keywords, "language": self.language},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(value.encode()).hexdigest()


class MetadataStore:
    """Append-only JSONL metadata store; records are never edited in place."""

    def __init__(self, path: Path, policy: PolicyBaseline | None = None):
        self.path = Path(path)
        self.policy = policy or PolicyBaseline()
        self._versions: dict[str, MetadataVersion] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    raw = json.loads(line)
                    self._versions[raw["version_id"]] = MetadataVersion(
                        **{**raw, "keywords": tuple(raw["keywords"]), "source": MetadataSource(raw["source"]), "status": MetadataStatus(raw["status"])}
                    )

    def _append(self, version: MetadataVersion) -> MetadataVersion:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({**asdict(version), "keywords": list(version.keywords), "source": version.source.value, "status": version.status.value}, sort_keys=True) + "\n")
        self._versions[version.version_id] = version
        return version

    def create(self, *, asset_id: str, artifact_hash: str, title: str, keywords: tuple[str, ...], source: MetadataSource, policy_version: str, valid: bool, language: str = "en", actor: str | None = None, reason: str | None = None) -> MetadataVersion:
        validation = validate_metadata(title, keywords, self.policy)
        version = MetadataVersion(str(uuid4()), asset_id, artifact_hash, title, tuple(keywords), language, source, MetadataStatus.PROPOSED, policy_version, valid and validation.passed, actor=actor, reason=reason)
        return self._append(version)

    def get(self, version_id: str) -> MetadataVersion:
        return self._versions[version_id]

    def approve(self, version_id: str, *, actor: str, reason: str) -> MetadataVersion:
        version = self.get(version_id)
        if not actor.strip() or not reason.strip():
            raise ValueError("approval requires actor and reason")
        if not version.valid:
            raise ValueError("invalid metadata cannot be approved")
        approved = MetadataVersion(**{**asdict(version), "source": MetadataSource.APPROVED, "status": MetadataStatus.APPROVED, "actor": actor, "reason": reason})
        return self._append(approved)

    def edit(self, version_id: str, *, title: str | None = None, keywords: tuple[str, ...] | None = None, actor: str, reason: str) -> MetadataVersion:
        parent = self.get(version_id)
        if parent.status is MetadataStatus.SUPERSEDED:
            raise ValueError("cannot edit superseded metadata")
        if not actor.strip() or not reason.strip():
            raise ValueError("metadata edits require actor and reason")
        superseded = MetadataVersion(**{**asdict(parent), "status": MetadataStatus.SUPERSEDED})
        self._append(superseded)
        return self.create(asset_id=parent.asset_id, artifact_hash=parent.artifact_hash, title=title if title is not None else parent.title, keywords=keywords if keywords is not None else parent.keywords, source=MetadataSource.USER_EDITED, policy_version=parent.policy_version, valid=True, language=parent.language, actor=actor, reason=reason)

    def current_approved(self, asset_id: str) -> MetadataVersion | None:
        candidates = [v for v in self._versions.values() if v.asset_id == asset_id and v.status is MetadataStatus.APPROVED]
        return max(candidates, key=lambda version: version.version_id, default=None)
