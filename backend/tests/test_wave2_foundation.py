from pathlib import Path

import pytest

from app.core.config import Settings, load_settings
from app.core.errors import ErrorCategory, StudioError
from app.core.storage import StorageLayout


def test_settings_reject_unsafe_upload_limit():
    with pytest.raises(ValueError, match="upload size"):
        Settings(max_upload_size_mb=0)


def test_storage_layout_keeps_all_locations_under_root(tmp_path: Path):
    layout = StorageLayout(tmp_path)

    assert layout.inbox.parent == tmp_path
    assert layout.thumbnails.parent == tmp_path
    assert layout.ready_to_upload.parent == tmp_path
    layout.ensure_exists()
    assert layout.inbox.is_dir()
    assert layout.quarantine.is_dir()
    assert layout.manifests.is_dir()


def test_error_exposes_safe_recovery_envelope():
    error = StudioError(
        category=ErrorCategory.RETRYABLE,
        code="PROVIDER_TIMEOUT",
        message="The provider is temporarily unavailable.",
        stage="semantic_audit",
        correlation_id="corr-123",
        detail="secret-token-must-not-be-in-message",
    )

    payload = error.to_dict()
    assert payload["code"] == "PROVIDER_TIMEOUT"
    assert payload["category"] == "retryable"
    assert "secret-token" not in str(payload)
    assert payload["correlation_id"] == "corr-123"


def test_environment_settings_are_typed_and_non_secret_diagnostics_are_safe(monkeypatch):
    monkeypatch.setenv("STUDIO_MAX_UPLOAD_SIZE_MB", "25")
    monkeypatch.setenv("STUDIO_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("STUDIO_GEMINI_API_KEY", "do-not-display")

    settings = load_settings()
    diagnostics = settings.diagnostics()

    assert settings.max_upload_size_mb == 25
    assert diagnostics["bind_host"] == "127.0.0.1"
    assert diagnostics["gemini_api_key_configured"] is True
    assert "do-not-display" not in str(diagnostics)
