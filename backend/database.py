"""Database engine, session factory, and base model for SQLAlchemy.

Per-platform DB isolation rule: **a platform's records never touch another
platform's engine.** The default ``engine``/``SessionLocal`` pair is the Adobe
Stock platform's (its URL points at ``settings.DB_PATH`` under
``storage/platforms/adobe_stock/``) and every other platform gets its own
engine + session factory via :func:`get_platform_engine` /
:func:`get_platform_session_factory`, each bound to that platform's dedicated
``<platform_id>.db`` (see :mod:`platforms.paths`). Sharing a session across
platforms would mix rows in one connection — never do it; open a session from
the owning platform's factory instead.
"""

from typing import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings
from platforms.paths import platform_db_path

#: The one platform whose engine is the module-level default. Adobe Stock is
#: the original pipeline, so it keeps the historical module-level ``engine`` /
#: ``SessionLocal`` names that the existing 60+ test files import.
ADOBE_STOCK_PLATFORM_ID = "adobe_stock"

# SQLite database URL (Adobe Stock platform — the default platform's DB)
DATABASE_URL = f"sqlite:///{settings.DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
    pool_pre_ping=True,
)


def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable WAL mode and other performance pragmas on every connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA busy_timeout=5000;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def _install_sqlite_pragmas(target_engine: Engine) -> None:
    """Attach the pragma listener to ``target_engine``.

    Single registration point used for the default engine (identical behavior
    to the historical ``@event.listens_for(engine, "connect")`` decorator —
    registered at import time, before any connection can be opened) and for
    every per-platform engine, so all SQLite connections — whichever platform
    they belong to — get WAL, NORMAL sync, a 5 s busy timeout, and enforced
    foreign keys.
    """
    event.listen(target_engine, "connect", set_sqlite_pragma)


_install_sqlite_pragmas(engine)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
    expire_on_commit=True,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Per-platform engines and session factories
# ---------------------------------------------------------------------------

#: Lazily created engines, keyed by platform id. Never cleared at runtime:
#: SQLAlchemy pools stay warm per platform, and each engine only ever opens
#: its own platform's file — the isolation guarantee is structural.
_PLATFORM_ENGINES: dict[str, Engine] = {}
#: Matching session factories (same kwargs as SessionLocal), keyed by platform.
_PLATFORM_FACTORIES: dict[str, sessionmaker] = {}


def get_platform_engine(platform_id: str) -> Engine:
    """Return the engine owning ``platform_id``'s database.

    Adobe Stock resolves to the default :data:`engine` (so legacy code keeps
    one canonical connection pool); any other platform gets a cached SQLite
    engine at ``storage/platforms/<id>/<id>.db`` with pragmas installed.
    """
    if platform_id == ADOBE_STOCK_PLATFORM_ID:
        return engine
    cached = _PLATFORM_ENGINES.get(platform_id)
    if cached is not None:
        return cached
    platform_engine = create_engine(
        f"sqlite:///{platform_db_path(platform_id)}",
        connect_args={"check_same_thread": False},
        echo=False,
        pool_pre_ping=True,
    )
    _install_sqlite_pragmas(platform_engine)
    _PLATFORM_ENGINES[platform_id] = platform_engine
    return platform_engine


def get_platform_session_factory(platform_id: str) -> sessionmaker:
    """Return a cached sessionmaker bound to ``platform_id``'s engine.

    Mirrors the :data:`SessionLocal` kwargs exactly (no autocommit, no
    autoflush, ``expire_on_commit=True``) so every platform behaves the same
    inside request handlers and background tasks.
    """
    cached = _PLATFORM_FACTORIES.get(platform_id)
    if cached is not None:
        return cached
    if platform_id == ADOBE_STOCK_PLATFORM_ID:
        # The default factory already IS the Adobe platform's factory.
        _PLATFORM_FACTORIES[platform_id] = SessionLocal
        return SessionLocal
    factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_platform_engine(platform_id),
        class_=Session,
        expire_on_commit=True,
    )
    _PLATFORM_FACTORIES[platform_id] = factory
    return factory


def init_platform_tables(platform_id: str) -> None:
    """Create every model table in ``platform_id``'s own database.

    ``models`` is imported lazily so ORM classes are registered on
    ``Base.metadata`` before ``create_all`` runs (importing it at module top
    would create a database <-> models import cycle).
    """
    import models  # noqa: F401  (registers ORM classes on Base.metadata)

    Base.metadata.create_all(bind=get_platform_engine(platform_id))
