"""Lightweight additive SQLite migrations.

The project intentionally avoids Alembic: this is a single-user local tool and
`Base.metadata.create_all` already covers fresh databases. This module only
patches *existing* databases with columns added after their creation.

Every migration must be additive and idempotent - it is safe to run on every
startup.
"""

import logging

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)


# (table, column, SQLite column definition)
ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("image_records", "is_used", "BOOLEAN NOT NULL DEFAULT 0"),
    ("image_records", "used_at", "DATETIME"),
]


def _existing_columns(engine: Engine, table: str) -> set[str]:
    """Return the set of column names currently present on a table."""
    with engine.connect() as connection:
        rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return {row[1] for row in rows}


def _table_exists(engine: Engine, table: str) -> bool:
    """Check whether a table exists in the SQLite schema."""
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table},
        ).fetchone()
    return row is not None


def run_additive_migrations(engine: Engine) -> list[str]:
    """Add any missing columns to existing tables.

    Returns the list of ``table.column`` identifiers that were added.
    """
    applied: list[str] = []

    for table, column, definition in ADDITIVE_COLUMNS:
        try:
            if not _table_exists(engine, table):
                continue
            if column in _existing_columns(engine, table):
                continue
            with engine.begin() as connection:
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                )
            applied.append(f"{table}.{column}")
            logger.info("Added missing column %s.%s", table, column)
        except Exception:  # pragma: no cover - defensive, never block startup
            logger.exception("Failed to add column %s.%s", table, column)

    return applied
