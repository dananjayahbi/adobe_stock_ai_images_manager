"""Managed storage layout and conservative filesystem helpers."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageLayout:
    root: Path

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def thumbnails(self) -> Path:
        return self.root / "thumbnails"

    @property
    def normalized(self) -> Path:
        return self.root / "normalized"

    @property
    def quarantine(self) -> Path:
        return self.root / "quarantine"

    @property
    def temporary(self) -> Path:
        return self.root / "tmp"

    @property
    def ready_to_upload(self) -> Path:
        return self.root / "ready_to_upload"

    @property
    def manifests(self) -> Path:
        return self.root / "manifests"

    @property
    def diagnostics(self) -> Path:
        return self.root / "diagnostics"

    @property
    def all_directories(self) -> tuple[Path, ...]:
        return (
            self.inbox,
            self.thumbnails,
            self.normalized,
            self.quarantine,
            self.temporary,
            self.ready_to_upload,
            self.manifests,
            self.diagnostics,
        )

    def ensure_exists(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in self.all_directories:
            directory.mkdir(parents=True, exist_ok=True)

    def contains(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root.resolve())
        except ValueError:
            return False
        return True

    def require_managed(self, path: Path) -> Path:
        resolved = path.resolve()
        if not self.contains(resolved):
            raise ValueError("path is outside the managed storage root")
        return resolved
