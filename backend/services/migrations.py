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
    # Stage pipeline columns. `stage` defaults to COLLECTED so pre-existing
    # rows (which only had `status`) enter the workspace at Stage 1.
    ("image_records", "stage", "VARCHAR(20) NOT NULL DEFAULT 'COLLECTED'"),
    ("image_records", "working_path", "VARCHAR(1024)"),
    ("image_records", "stage_updated_at", "DATETIME"),
    ("image_records", "acceptance_report", "JSON"),
    ("image_records", "acceptance_score", "FLOAT"),
    ("image_records", "refine_passes", "INTEGER NOT NULL DEFAULT 0"),
    ("image_records", "stage_details", "JSON"),
    ("image_records", "category", "INTEGER"),
    ("image_records", "queued_stage", "VARCHAR(20)"),
]

# Rows that already reached READY under the old two-column model are already
# published; align their stage so the workspace does not show them as new.
BACKFILL_STATEMENTS: list[str] = [
    "UPDATE image_records SET stage = 'PUBLISHED' WHERE status = 'READY'",
    "UPDATE image_records SET stage = 'INCOMPATIBLE' WHERE status = 'FLAGGED'",
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

    When the ``stage`` column is created for the first time, pre-existing rows
    are backfilled so records that were already READY/FLAGGED keep their
    meaning instead of appearing as fresh Stage 1 entries.
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

    # Backfill only when the stage column was introduced by this run, so an
    # operator's manual stage changes are never overwritten on later starts.
    if "image_records.stage" in applied:
        for statement in BACKFILL_STATEMENTS:
            try:
                with engine.begin() as connection:
                    connection.execute(text(statement))
                logger.info("Backfilled stages with: %s", statement)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Failed to run backfill: %s", statement)

    return applied
