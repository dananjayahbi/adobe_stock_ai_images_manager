"""Pytest configuration and shared fixtures for the backend test suite."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the flat backend package layout is importable.
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture()
def db_session_factory():
    """In-memory SQLite session factory isolated per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import models  # noqa: F401  (register tables)

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session_factory, monkeypatch, tmp_path):
    """TestClient with the DB dependency overridden and background audits stubbed."""

    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Redirect storage writes into the test's temp directory.
    from config import settings

    inbox = tmp_path / "inbox"
    thumbnails = tmp_path / "thumbnails"
    ready = tmp_path / "ready"
    refined = tmp_path / "refined"
    upscaled = tmp_path / "upscaled"
    for directory in (inbox, thumbnails, ready, refined, upscaled):
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "INBOX_DIR", inbox)
    monkeypatch.setattr(settings, "THUMBNAILS_DIR", thumbnails)
    monkeypatch.setattr(settings, "READY_DIR", ready)
    monkeypatch.setattr(settings, "REFINED_DIR", refined)
    monkeypatch.setattr(settings, "UPSCALED_DIR", upscaled)

    # Upload is Stage 1 only and schedules no background work, so no audit
    # stubbing is needed here. Stage operations are dispatched explicitly by
    # the caller and are tested through the orchestrator directly.

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture()
def sample_jpeg(tmp_path):
    """Create a real 2000x2000 JPEG (4.0 MP) with visible detail."""

    def _make(
        width: int = 2000,
        height: int = 2000,
        solid: bool = False,
        name: str = "sample.jpg",
    ) -> Path:
        path = tmp_path / name
        image = Image.new("RGB", (width, height), color=(128, 128, 128))
        if not solid:
            pixels = image.load()
            for y in range(0, height, 4):
                for x in range(0, width, 4):
                    value = 255 if ((x // 4) + (y // 4)) % 2 == 0 else 0
                    for dy in range(4):
                        for dx in range(4):
                            if x + dx < width and y + dy < height:
                                pixels[x + dx, y + dy] = (value, value, value)
        image.save(path, "JPEG", quality=95)
        return path

    return _make
