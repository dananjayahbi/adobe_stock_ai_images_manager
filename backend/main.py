"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import Base, engine
from services.metric_repair import run_metric_repairs
from services.migrations import run_additive_migrations
from services.pipeline_runner import recover_interrupted_batches
from services.storage import create_data_directories


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: create DB tables and data directories."""
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
    # Batch jobs live in memory: a restart orphans any batch left `running`,
    # which would read as a hung run forever and block re-runs. Fail them once.
    recover_interrupted_batches(engine)
    yield
    # Shutdown cleanup if needed


app = FastAPI(
    title="Adobe Stock AI Image Studio",
    description="Local pipeline for auditing and preparing AI-generated images for Adobe Stock.",
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


@app.get("/health")
def health_check():
    return {"status": "ok"}
