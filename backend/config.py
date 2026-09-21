"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve repo root (one level above backend/)
REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = REPO_ROOT / "storage"


class Settings(BaseSettings):
    """Centralized application settings with QC thresholds for Adobe Stock compliance."""

    # ------------------------------------------------------------------ #
    # Server / CORS
    # ------------------------------------------------------------------ #
    #: Port the API listens on. Kept in config rather than only on the uvicorn
    #: command line so the CORS default below can stay in step with it.
    BACKEND_PORT: int = 8100
    #: Origins allowed to call the API. The frontend runs on a different port,
    #: so browsers block its requests unless the exact origin is listed here.
    #: Override with a JSON array or comma-separated string in .env.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3100",
        "http://127.0.0.1:3100",
    ]

    # LLM gateway (OpenAI-compatible). These are the *defaults*: the operator
    # can override base URL, model, key, and context window from the Settings
    # modal, which persists to APP_SETTINGS_PATH (see services/app_settings.py).
    LLM_BASE_URL: str = "http://localhost:4006/api/gateway/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "OpenRouter-Free-Endpoint"
    LLM_TIMEOUT_SECONDS: int = 240
    #: Preferred long edge for an image sent to a vision model. A hard ceiling:
    #: a context window small enough to overflow steps this down, never up.
    LLM_IMAGE_MAX_DIM: int = 1024
    #: Fallback context window when the operator has not declared one. Kept
    #: deliberately small so an unknown model is never assumed to be large.
    LLM_CONTEXT_WINDOW: int = 32_768

    #: JSON document holding operator-editable settings. Lives beside the DB so
    #: one storage directory holds all mutable state.
    APP_SETTINGS_PATH: Path = STORAGE_ROOT / "app_settings.json"

    # Legacy Gemini key. Retained only as a fallback source for LLM_API_KEY so
    # existing .env files keep working.
    GEMINI_API_KEY: str = ""

    # Storage directories (resolved relative to repo root)
    INBOX_DIR: Path = STORAGE_ROOT / "inbox"
    THUMBNAILS_DIR: Path = STORAGE_ROOT / "thumbnails"
    READY_DIR: Path = STORAGE_ROOT / "ready_to_upload"
    #: Where the refiner writes corrected copies (originals are never mutated).
    REFINED_DIR: Path = STORAGE_ROOT / "refined"
    #: Where the upscaler writes upscaled copies.
    UPSCALED_DIR: Path = STORAGE_ROOT / "upscaled"

    # Database
    DB_PATH: Path = STORAGE_ROOT / "adobe_stock.db"

    # QC Thresholds - Adobe Stock baselines
    MIN_MEGAPIXELS: float = 4.0
    MAX_MEGAPIXELS: float = 100.0
    TARGET_MIN_MP: float = 15.0
    TARGET_MAX_MP: float = 25.0
    MIN_LAPLACIAN_VARIANCE: float = 120.0
    MIN_SEMANTIC_CONFIDENCE: float = 0.75

    # Stage 4/5 acceptance gate. An image must reach this score to advance.
    ACCEPTANCE_THRESHOLD: float = 0.80
    #: Maximum auto-refinement passes before the image is marked INCOMPATIBLE.
    MAX_REFINE_PASSES: int = 4
    #: JPEG quality used when re-encoding refined/upscaled images (4:4:4 chroma).
    EXPORT_JPEG_QUALITY: int = 95

    # File size constraints (in MB)
    MIN_FILE_SIZE_MB: int = 5
    MAX_FILE_SIZE_MB: int = 35
    ABSOLUTE_MAX_FILE_SIZE_MB: int = 45

    # Allowed file extensions. PNG is accepted at the Collector and normalised to
    # JPEG immediately afterwards (see services/image_normalizer.py), because
    # Adobe rejects PNG for photos but AI tools commonly emit it.
    ALLOWED_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png"}
    #: Extensions the Collector converts to JPEG on ingestion.
    PNG_EXTENSIONS: set[str] = {".png"}
    #: Where normalised JPEG copies are written. Kept separate from the inbox so
    #: the uploaded original stays byte-for-byte intact as the audit source.
    CONVERTED_DIR: Path = STORAGE_ROOT / "converted"
    #: Quality for the PNG -> JPEG conversion. 100 keeps the result visually
    #: lossless so the conversion cannot itself introduce an acceptance issue.
    PNG_CONVERSION_QUALITY: int = 100

    # Colour space requirement
    REQUIRED_COLOR_SPACE: str = "sRGB"

    # Queue limit for batch packaging
    READY_QUEUE_LIMIT: int = 50

    # ------------------------------------------------------------------ #
    # Adobe Stock published limits (verified against helpx, 2026-09)
    # Source: technical-legal-requirements-photo-submission.html,
    #         csv-requirements-content.html, tips-effective-titles-keywords.html
    # ------------------------------------------------------------------ #

    #: Photos: JPEG only, 4-100 MP, max 45 MB, sRGB profile required.
    ADOBE_MIN_MEGAPIXELS: float = 4.0
    ADOBE_MAX_MEGAPIXELS: float = 100.0
    ADOBE_MAX_FILE_SIZE_MB: float = 45.0

    #: CSV export limits. Exceeding any of these makes Adobe reject the file
    #: outright, so the exporter truncates and reports rather than emitting it.
    CSV_MAX_ROWS: int = 5_000
    CSV_MAX_FILE_SIZE_BYTES: int = 1_000_000  # 1 MB
    #: Filename and Title are hard-truncated to Adobe's published lengths.
    CSV_MAX_FILENAME_LENGTH: int = 30
    CSV_MAX_TITLE_LENGTH: int = 70
    #: Keywords: the CSV page says 50, the titles/keywords page and the portal
    #: dialog say 49. The lower, more specific figure is the safe one.
    CSV_MAX_KEYWORDS: int = 49
    #: The first 10 keywords carry the most search weight, so the generator is
    #: told to front-load the most relevant terms.
    KEYWORDS_HIGH_IMPACT: int = 10

    #: Detach the refined/upscaled export from any source ICC profile and embed
    #: sRGB explicitly. Adobe requires "JPEG with sRGB color profile", and a
    #: colour-space mismatch is a documented refusal reason.
    EMBED_SRGB_PROFILE: bool = True

    # ------------------------------------------------------------------ #
    # Stage pipeline
    # ------------------------------------------------------------------ #

    #: Stage 3 - Upscayl CLI. This is the headless ncnn binary that ships inside
    #: the app, not ``Upscayl.exe`` (that is the Electron GUI, which ignores CLI
    #: flags). Override to point at another build; ``find_cli`` also accepts the
    #: app folder and probes ``resources/bin`` itself.
    UPSCAYL_EXE: Path = (
        REPO_ROOT
        / "backend"
        / "upscayl-2.15.0"
        / "resources"
        / "bin"
        / "upscayl-bin.exe"
    )
    #: Preferred model. 4xNomos8kSC is the strongest general photographic model
    #: in the outsourced set; if it is absent the catalog falls back through a
    #: documented order so a checkout without Outsourced_models still works.
    UPSCAYL_MODEL: str = "4xNomos8kSC"
    UPSCAYL_SCALE: int = 4
    UPSCAYL_TIMEOUT_SECONDS: int = 600
    #: Folder that holds the bundled app. The headless binary is discovered at
    #: ``resources/bin/upscayl-bin.exe`` and the models in ``resources/models``
    #: plus ``Outsourced_models/models``.
    UPSCAYL_APP_DIR: Path = REPO_ROOT / "backend" / "upscayl-2.15.0"
    #: Extra model folders to scan, on top of the two bundled locations.
    UPSCAYL_MODEL_DIRS: list[Path] = []
    #: Vulkan device id. 0 is the dedicated GPU on this machine; the integrated
    #: Intel devices enumerate as 1-3.
    UPSCAYL_GPU_ID: int = 0
    #: Default long edge for the Stage 3 capacity picker (4K).
    UPSCAYL_TARGET_LONG_EDGE: int = 3840
    #: Test-time augmentation. Better edges, markedly slower - off by default.
    UPSCAYL_TTA: bool = False

    #: Stage 6 - pause between LLM metadata calls, in seconds, to dodge rate limits.
    METADATA_CALL_DELAY_SECONDS: float = 2.0
    #: Default number of keywords requested from the metadata model.
    METADATA_KEYWORD_TARGET: int = 30

    #: Adobe Stock category assigned when the model's suggestion is unusable.
    DEFAULT_ADOBE_CATEGORY: int = 8

    model_config = {
        # Accept .env at the repo root or beside the backend code; backend/ wins.
        "env_file": (str(REPO_ROOT / ".env"), str(REPO_ROOT / "backend" / ".env")),
        "env_file_encoding": "utf-8",
    }

    @property
    def effective_llm_api_key(self) -> str:
        """Environment-level gateway key, falling back to the legacy GEMINI_API_KEY.

        This is only one of three layers. Call
        :func:`services.app_settings.resolve` to get the key a request should
        actually use, because an operator-saved key in the Settings modal takes
        precedence over this one.
        """
        return self.LLM_API_KEY or self.GEMINI_API_KEY


settings = Settings()
