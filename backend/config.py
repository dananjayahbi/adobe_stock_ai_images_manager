"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve repo root (one level above backend/)
REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = REPO_ROOT / "storage"


class Settings(BaseSettings):
    """Centralized application settings with QC thresholds for Adobe Stock compliance."""

    # LLM gateway (OpenAI-compatible). Defaults to the local multi-provider router.
    LLM_BASE_URL: str = "http://localhost:4006/api/gateway/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "OpenRouter-Free-Endpoint"
    LLM_TIMEOUT_SECONDS: int = 240
    # Images are downscaled before upload to keep requests small and fast.
    LLM_IMAGE_MAX_DIM: int = 1024

    # Legacy Gemini key. Retained only as a fallback source for LLM_API_KEY so
    # existing .env files keep working.
    GEMINI_API_KEY: str = ""

    # Storage directories (resolved relative to repo root)
    INBOX_DIR: Path = STORAGE_ROOT / "inbox"
    THUMBNAILS_DIR: Path = STORAGE_ROOT / "thumbnails"
    READY_DIR: Path = STORAGE_ROOT / "ready_to_upload"

    # Database
    DB_PATH: Path = STORAGE_ROOT / "adobe_stock.db"

    # QC Thresholds - Adobe Stock baselines
    MIN_MEGAPIXELS: float = 4.0
    TARGET_MIN_MP: float = 15.0
    TARGET_MAX_MP: float = 25.0
    MIN_LAPLACIAN_VARIANCE: float = 120.0
    MIN_SEMANTIC_CONFIDENCE: float = 0.75

    # File size constraints (in MB)
    MIN_FILE_SIZE_MB: int = 5
    MAX_FILE_SIZE_MB: int = 35
    ABSOLUTE_MAX_FILE_SIZE_MB: int = 45

    # Allowed file extensions
    ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg"}

    # Color space requirement
    REQUIRED_COLOR_SPACE: str = "sRGB"

    # Queue limit for batch packaging
    READY_QUEUE_LIMIT: int = 50

    model_config = {
        # Accept .env at the repo root or beside the backend code; backend/ wins.
        "env_file": (str(REPO_ROOT / ".env"), str(REPO_ROOT / "backend" / ".env")),
        "env_file_encoding": "utf-8",
    }

    @property
    def effective_llm_api_key(self) -> str:
        """Gateway key, falling back to the legacy GEMINI_API_KEY."""
        return self.LLM_API_KEY or self.GEMINI_API_KEY


settings = Settings()
