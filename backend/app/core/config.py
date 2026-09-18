"""Validated runtime configuration for the local desktop deployment."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    storage_root: Path = Path("backend/storage")
    bind_host: str = "127.0.0.1"
    port: int = 8000
    max_upload_size_mb: int = 45
    max_batch_size: int = 50
    worker_concurrency: int = 1
    provider_enabled: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    policy_version: str = "wave1-baseline-2026-09"
    log_level: str = "INFO"

    def __post_init__(self) -> None:
        if self.bind_host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("bind_host must remain localhost unless LAN access is explicitly designed")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.max_upload_size_mb < 1:
            raise ValueError("upload size must be at least 1 MB")
        if not 1 <= self.max_batch_size <= 500:
            raise ValueError("batch size must be between 1 and 500")
        if not 1 <= self.worker_concurrency <= 8:
            raise ValueError("worker concurrency must be between 1 and 8")

    @property
    def effective_provider_enabled(self) -> bool:
        return self.provider_enabled and bool(self.gemini_api_key)

    def diagnostics(self) -> dict[str, object]:
        return {
            "storage_root": str(self.storage_root),
            "bind_host": self.bind_host,
            "port": self.port,
            "max_upload_size_mb": self.max_upload_size_mb,
            "max_batch_size": self.max_batch_size,
            "worker_concurrency": self.worker_concurrency,
            "provider_enabled": self.provider_enabled,
            "gemini_api_key_configured": bool(self.gemini_api_key),
            "gemini_model": self.gemini_model,
            "policy_version": self.policy_version,
            "log_level": self.log_level,
        }


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    return Settings(
        storage_root=Path(os.getenv("STUDIO_STORAGE_ROOT", "backend/storage")),
        bind_host=os.getenv("STUDIO_BIND_HOST", "127.0.0.1"),
        port=_env_int("STUDIO_PORT", 8000),
        max_upload_size_mb=_env_int("STUDIO_MAX_UPLOAD_SIZE_MB", 45),
        max_batch_size=_env_int("STUDIO_MAX_BATCH_SIZE", 50),
        worker_concurrency=_env_int("STUDIO_WORKER_CONCURRENCY", 1),
        provider_enabled=_env_bool("STUDIO_PROVIDER_ENABLED", False),
        gemini_api_key=os.getenv("STUDIO_GEMINI_API_KEY"),
        gemini_model=os.getenv("STUDIO_GEMINI_MODEL", "gemini-2.5-flash"),
        policy_version=os.getenv("STUDIO_POLICY_VERSION", "wave1-baseline-2026-09"),
        log_level=os.getenv("STUDIO_LOG_LEVEL", "INFO").upper(),
    )
