"""Application configuration loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve repo root (one level above backend/)
REPO_ROOT = Path(__file__).resolve().parent.parent
STORAGE_ROOT = REPO_ROOT / "storage"
# Universal multi-platform layout: every platform owns a dedicated subdirectory
# under storage/platforms/ holding ITS data directories and ITS SQLite database
# (zero data leakage between platforms — see platforms/paths.py). APP_SETTINGS_PATH
# deliberately stays at STORAGE_ROOT because operator settings are app-level, not
# platform data.
PLATFORMS_ROOT = STORAGE_ROOT / "platforms"
#: The one platform that exists today. All Settings dir fields below point here,
#: so the existing (Adobe Stock-only) pipeline keeps working unchanged while the
# rest of the app migrates to platforms.paths.get_platform_paths().
ADOBE_STOCK_ROOT = PLATFORMS_ROOT / "adobe_stock"


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

    #: JSON document holding operator-editable settings. Lives at the storage
    #: ROOT (not inside a platform directory): it is app-level configuration
    #: shared across platforms, so it must never be migrated with platform data.
    APP_SETTINGS_PATH: Path = STORAGE_ROOT / "app_settings.json"

    # ------------------------------------------------------------------ #
    # Web search (the research agent's evidence source)
    # ------------------------------------------------------------------ #
    #: Whether the operator has enabled Brave Search as the primary provider.
    #: Default **off**, so a deployment with no key behaves exactly as before the
    #: feature existed. Stored per-operator in the settings store, not here.
    BRAVE_SEARCH_ENABLED: bool = False
    #: Brave Search API key. Read from ``.env`` when the operator has not stored
    #: one in the settings store, exactly like ``LLM_API_KEY``.
    BRAVE_SEARCH_API_KEY: str = ""
    #: Requests per second Brave's plan allows. Used to space out the queries one
    #: ``market_overview`` call issues, which is what actually trips a 429.
    BRAVE_SEARCH_RATE_LIMIT_PER_SECOND: float = 1.0

    # Legacy Gemini key. Retained only as a fallback source for LLM_API_KEY so
    # existing .env files keep working.
    GEMINI_API_KEY: str = ""

    # Storage directories (Adobe Stock platform data; defaults resolve to
    # <repo>/storage/platforms/adobe_stock/... — see .env.example). Field names
    # must not change: 40+ services read settings.INBOX_DIR etc. Future platforms
    # must NOT override these; they use platforms.paths.get_platform_paths().
    INBOX_DIR: Path = ADOBE_STOCK_ROOT / "inbox"
    THUMBNAILS_DIR: Path = ADOBE_STOCK_ROOT / "thumbnails"
    READY_DIR: Path = ADOBE_STOCK_ROOT / "ready_to_upload"
    #: Where the refiner writes corrected copies (originals are never mutated).
    REFINED_DIR: Path = ADOBE_STOCK_ROOT / "refined"
    #: Where the upscaler writes upscaled copies.
    UPSCALED_DIR: Path = ADOBE_STOCK_ROOT / "upscaled"

    # Database (per-platform: the Adobe Stock DB lives in its platform root so
    # every platform keeps its own <platform_id>.db — see platforms/paths.py).
    DB_PATH: Path = ADOBE_STOCK_ROOT / "adobe_stock.db"

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
    CONVERTED_DIR: Path = ADOBE_STOCK_ROOT / "converted"
    #: RGBA cut-outs written by the PNG batch background remover.
    REMOVED_DIR: Path = ADOBE_STOCK_ROOT / "removed"
    #: Raster images whose background was verified/clamped to pure #FFFFFF.
    WHITE_DIR: Path = ADOBE_STOCK_ROOT / "white"
    #: Files written by the `embed_srgb` step (tagged copies when the input
    #: profile was missing — kept separate so the source is never mutated).
    SRGB_DIR: Path = ADOBE_STOCK_ROOT / "srgb"
    #: Near-duplicate variants quarantined by the batch diversity gate. Kept on
    #: disk (never deleted by the step) so they can seed a later batch.
    QUARANTINE_DIR: Path = ADOBE_STOCK_ROOT / "quarantine"
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

    #: CSV export limits. Exceeding CSV_MAX_ROWS/CSV_MAX_FILE_SIZE_BYTES makes
    #: Adobe reject the file outright, so the exporter truncates and reports
    #: rather than emitting it.
    CSV_MAX_ROWS: int = 5_000
    CSV_MAX_FILE_SIZE_BYTES: int = 1_000_000  # 1 MB
    #: Adobe's console *lists* "Filename: 30 characters maximum", but that figure
    #: is advisory guidance, not a portal limit: the uploader accepts longer
    #: names, and the hard requirement is that the CSV Filename matches the
    #: uploaded file exactly. The tool therefore keeps the full descriptive name
    #: (titles stay within the real 70-char limit) and only caps at a
    #: filesystem-safe length. Title is genuinely hard-capped by Adobe at 70.
    CSV_MAX_FILENAME_LENGTH: int = 100
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
    #: This is the *settings default* (the Settings page can override it per
    #: install); it must match what the generator actually did before the
    #: setting existed - up to Adobe's 49-keyword ceiling - or enabling the
    #: setting would silently halve every batch's keywords.
    METADATA_KEYWORD_TARGET: int = 49

    #: Adobe Stock category assigned when the model's suggestion is unusable.
    DEFAULT_ADOBE_CATEGORY: int = 8

    model_config = {
        # Accept .env at the repo root or beside the backend code; backend/ wins.
        "env_file": (str(REPO_ROOT / ".env"), str(REPO_ROOT / "backend" / ".env")),
        "env_file_encoding": "utf-8",
        # .env carries keys this class does not model (e.g. the AUTH_* block
        # documented in .env.example — see auth_config.py). pydantic-settings
        # defaults to extra="forbid", which turns any such variable into a
        # ValidationError at import; ignore extras so documented-but-unmodeled
        # keys can live in .env safely.
        "extra": "ignore",
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

# ---------------------------------------------------------------------------
# Model storage
# ---------------------------------------------------------------------------
# Every downloaded weight lives under <repo>/models so the whole setup can be
# copied to another machine as a single folder (see services/model_paths).
#
# Applied here, at config import — which happens before anything pulls in rembg
# or transformers — because those libraries read their home directories the
# first time they resolve a model. Both rembg variables are defaulted, so an
# explicitly exported U2NET_HOME still wins.
from services import model_paths  # noqa: E402  (side-effect import, by design)

model_paths.apply_env()
