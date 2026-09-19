"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import Base, engine
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
    yield
    # Shutdown cleanup if needed


app = FastAPI(
    title="Adobe Stock AI Image Studio",
    description="Local pipeline for auditing and preparing AI-generated images for Adobe Stock.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow localhost:3000 for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from routers.upload import router as upload_router
from routers.records import router as records_router
from routers.approve import router as approve_router
from routers.gallery import router as gallery_router

app.include_router(upload_router)
app.include_router(records_router)
app.include_router(approve_router)
app.include_router(gallery_router)

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
