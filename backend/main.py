"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import Base, engine
from services.filename_backfill import run_filename_backfill
from services.legacy_storage_migration import run_legacy_storage_migration
from services.metric_repair import run_metric_repairs
from services.migrations import run_additive_migrations
from services.pipeline_runner import recover_interrupted_batches
from services.storage import create_data_directories


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: create DB tables and data directories."""
    # One-time move of legacy storage/* data into the Adobe platform root.
    # FIRST action: it must run before create_data_directories() builds the
    # destination skeleton and before Base.metadata.create_all opens the new
    # DB path. Self-limiting — the .migrated marker makes later starts no-op,
    # and failures are logged without crashing so the next start retries.
    run_legacy_storage_migration()
    # Import models to ensure they are registered with Base.metadata
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # Patch pre-existing databases with columns added after their creation.
    run_additive_migrations(engine)
    create_data_directories()
    # Records written before the metrics were measured on the *deliverable* file
    # carry the original upload's geometry and size. Repair them once; the pass
    # is self-limiting, so later starts do nothing.
    run_metric_repairs(engine)
    # Records pinned by an old CSV download still carry the pre-raise
    # 30-character filename; upgrade those pins to the full derived name
    # (self-limiting — hand-chosen names never match the old truncation).
    run_filename_backfill(engine)
    # Batch jobs live in memory: a restart orphans any batch left `running`,
    # which would read as a hung run forever and block re-runs. Fail them once.
    recover_interrupted_batches(engine)
    yield
    # Shutdown cleanup if needed


app = FastAPI(
    title="AI Stock Studio",
    description="Universal local pipeline for preparing AI-generated images for stock marketplaces (Adobe Stock first).",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - the allowed origins come from settings so the frontend
# port can change without editing code (see CORS_ORIGINS in config.py).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session-cookie auth: installed after CORS so preflight responses are not
# blocked, and before routers so every route is covered when AUTH_ENABLED.
from services.auth_middleware import install_auth_middleware

install_auth_middleware(app)

# Include routers
from routers.upload import router as upload_router
from routers.records import router as records_router
from routers.approve import router as approve_router
from routers.gallery import router as gallery_router
from routers.similarity import router as similarity_router
from routers.stages import router as stages_router
from routers.queues import router as queues_router
from routers.autofix import router as autofix_router
from routers.settings import router as settings_router
from routers.prompts import router as prompts_router
from routers.delivery import router as delivery_router
from routers.research import router as research_router
from routers.batches import router as batches_router
from routers.step_profiles import router as step_profiles_router
from routers.groups import router as groups_router
from routers.gallery_files import router as gallery_files_router
from routers.setup import router as setup_router
from routers.promote import router as promote_router
from platforms.routers import router as platforms_router
from routers.auth import router as auth_router

app.include_router(upload_router)
app.include_router(records_router)
app.include_router(approve_router)
app.include_router(gallery_router)
app.include_router(similarity_router)
app.include_router(stages_router)
app.include_router(queues_router)
app.include_router(autofix_router)
app.include_router(settings_router)
app.include_router(prompts_router)
app.include_router(delivery_router)
app.include_router(research_router)
app.include_router(batches_router)
app.include_router(step_profiles_router)
app.include_router(groups_router)
app.include_router(gallery_files_router)
app.include_router(setup_router)
app.include_router(promote_router)
app.include_router(platforms_router)
app.include_router(auth_router)

# Serve generated thumbnails to the frontend grid.
create_data_directories()


@app.middleware("http")
async def thumbnails_must_revalidate(request, call_next):
    """Thumbnails are rewritten *in place* (bg removal overwrites thumb_{id}.png).

    Without an explicit directive the browser heuristically caches them, so a
    freshly produced cut-out keeps showing the previous image until a manual
    reload forces revalidation. ``no-cache`` keeps cheap ETag/Last-Modified 304s
    while guaranteeing an overwritten file is picked up immediately.
    """
    response = await call_next(request)
    if request.url.path.startswith("/thumbnails"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount(
    "/thumbnails",
    StaticFiles(directory=str(settings.THUMBNAILS_DIR)),
    name="thumbnails",
)

# Serve the Flutter web build under /flutter so the mobile app rides the
# *same origin as the API* through the Cloudflare tunnel (cookie-auth and
# CSP-free by construction). Guarded: the directory only exists after
# `flutter build web` — without it the mount is skipped, never fatal.
from pathlib import Path as _Path

_FLUTTER_WEB_DIR = _Path(__file__).resolve().parent.parent / "mobile" / "build" / "web"
if _FLUTTER_WEB_DIR.is_dir():
    app.mount(
        "/flutter",
        StaticFiles(directory=str(_FLUTTER_WEB_DIR), html=True),
        name="flutter",
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}
