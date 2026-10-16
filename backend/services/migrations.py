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
    # Prompt Library link (Stage 1). Nullable: an image may be collected
    # without a known prompt, and one prompt binds to many images.
    ("image_records", "prompt_id", "VARCHAR(36)"),
    # Operator-chosen upload filename (Stage 6). NULL means "derive it from the
    # title", so existing rows keep their current names with no backfill.
    ("image_records", "download_name", "VARCHAR(255)"),
    # Upload filename proposed by the metadata model (Stage 6). NULL for every
    # record generated before the model was asked to name the asset, which falls
    # back to the title-derived name with no backfill needed.
    ("image_records", "suggested_filename", "VARCHAR(255)"),
    # Batch membership (batch pipeline v2). NULL for records created outside a
    # batch, so the legacy stage workspace keeps working unchanged.
    ("image_records", "batch_id", "VARCHAR(36)"),
    # Gallery folder membership. NULL = ungrouped (top level of the gallery).
    ("image_records", "group_id", "VARCHAR(36)"),
    # Lifecycle state (publish/download flow). Defaults to COLLECTED so
    # pre-existing rows enter at "not processed yet"; the backfill below
    # re-derives the meaning the old status/stage pair already carried.
    ("image_records", "state", "VARCHAR(20) NOT NULL DEFAULT 'COLLECTED'"),
    # Prompt Library folders. NULL = ungrouped; the name IS the folder, so a
    # batch can be isolated the moment its prompts are assigned.
    ("prompts", "group_name", "VARCHAR(120)"),
]

# Rows that already reached READY under the old two-column model are already
# published; align their stage so the workspace does not show them as new.
BACKFILL_STATEMENTS: list[str] = [
    "UPDATE image_records SET stage = 'PUBLISHED' WHERE status = 'READY'",
    "UPDATE image_records SET stage = 'INCOMPATIBLE' WHERE status = 'FLAGGED'",
]

# Precedence-ordered mapping from the old two-column model onto `state`,
# run on EVERY startup as an idempotent repair (the live database may have
# gained the column on a run that predated this block, so a
# freshly-added-column gate would skip it forever).
# Every statement is guarded so a rerun can never overwrite a decision:
# derivation rules only touch rows still in `state = 'COLLECTED'` (the
# column default — manual states are never COLLECTED), and the trailing
# used-push rule only ever moves `is_used` rows into PUBLISHED while
# leaving AS_ACCEPTED alone. AS_ACCEPTED starts empty — it is only ever
# set manually.
STATE_BACKFILL_STATEMENTS: list[str] = [
    (
        "UPDATE image_records SET state = 'PUBLISHED' "
        "WHERE stage = 'PUBLISHED' AND state = 'COLLECTED'"
    ),
    (
        "UPDATE image_records SET state = 'READY_TO_PUBLISH' "
        "WHERE status = 'READY' AND state = 'COLLECTED'"
    ),
    (
        "UPDATE image_records SET state = 'REJECTED' "
        "WHERE (status = 'FLAGGED' OR stage IN "
        "('OCR_REJECTED', 'INCOMPATIBLE', 'QUARANTINED')) "
        "AND state = 'COLLECTED'"
    ),
    (
        "UPDATE image_records SET state = 'APPROVED' "
        "WHERE stage = 'METADATA_READY' AND state = 'COLLECTED'"
    ),
    # Rule 04: Used images live only in PUBLISHED / AS_ACCEPTED — re-asserted
    # every start so legacy `is_used` rows (and any drift) get pushed.
    (
        "UPDATE image_records SET state = 'PUBLISHED' "
        "WHERE is_used = 1 AND state NOT IN ('PUBLISHED', 'AS_ACCEPTED')"
    ),
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
    meaning instead of appearing as fresh Stage 1 entries. The ``state``
    mapping runs every startup as a guarded, idempotent repair (see
    ``STATE_BACKFILL_STATEMENTS``).
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

    # Same freshly-added-column idiom for `state` would be a trap in
    # practice: the live database's column may have been created by a run
    # that predated this block, and a fresh-gate then skips it forever.
    # The statements themselves are fully guarded (COLLECTED-only + the
    # narrow used-push), so they run every startup as a safe, self-healing
    # repair. Must run *after* the stage backfill above (reads `stage`).
    for statement in STATE_BACKFILL_STATEMENTS:
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
            logger.info("Backfilled states with: %s", statement)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to run backfill: %s", statement)
    # `ALTER TABLE ADD COLUMN` cannot create the model's index, so a
    # migrated database gets it here (idempotent).
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_image_records_state "
                    "ON image_records (state)"
                )
            )
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to create index ix_image_records_state")

    return applied
