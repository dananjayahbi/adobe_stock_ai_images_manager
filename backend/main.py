"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import Base, engine
from services.metric_repair import run_metric_repairs
from services.migrations import run_additive_migrations
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

# Serve generated thumbnails to the frontend grid.
create_data_directories()
app.mount(
    "/thumbnails",
    StaticFiles(directory=str(settings.THUMBNAILS_DIR)),
    name="thumbnails",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}
