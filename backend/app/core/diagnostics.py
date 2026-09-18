"""Local-first health checks and redacted operational diagnostics."""

from dataclasses import dataclass
from pathlib import Path
import shutil

from .config import Settings
from .storage import StorageLayout


@dataclass(frozen=True)
class HealthStatus:
    name: str
    status: str
    detail: str


def check_health(settings: Settings, layout: StorageLayout) -> tuple[HealthStatus, ...]:
    checks = [
        HealthStatus("liveness", "ok", "process is running"),
        HealthStatus(
            "storage",
            "ok" if layout.root.exists() and layout.contains(layout.root) else "degraded",
            str(layout.root),
        ),
        HealthStatus(
            "disk",
            "ok" if shutil.disk_usage(layout.root if layout.root.exists() else Path.cwd()).free > 0 else "degraded",
            "free space available",
        ),
        HealthStatus(
            "provider",
            "configured" if settings.effective_provider_enabled else "disabled",
            "provider is optional for deterministic QC",
        ),
    ]
    return tuple(checks)


def diagnostic_snapshot(settings: Settings, layout: StorageLayout) -> dict[str, object]:
    return {
        "configuration": settings.diagnostics(),
        "health": [health.__dict__ for health in check_health(settings, layout)],
        "storage_directories": [str(path) for path in layout.all_directories],
    }
