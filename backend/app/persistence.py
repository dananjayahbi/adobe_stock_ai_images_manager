"""SQLite persistence for Wave 3 entities, provenance, and lifecycle events."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.core.workflow import AssetStatus, InvalidTransition, transition


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class AssetCreateResult:
    asset_id: str
    duplicate: bool


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection.execute("CREATE TABLE IF NOT EXISTS schema_meta (version INTEGER NOT NULL)")
        row = self.connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        if row and row["version"] > SCHEMA_VERSION:
            raise RuntimeError("database schema is newer than this application")
        if not row:
            self.connection.execute("INSERT INTO schema_meta(version) VALUES (?)", (0,))
        if self.schema_version() < 1:
            self._migration_1()
        self.connection.commit()

    def schema_version(self) -> int:
        row = self.connection.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()
        return int(row["version"]) if row else 0

    def _migration_1(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                filename TEXT NOT NULL, source_hash TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_assets_status_updated ON assets(status, updated_at);
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
                role TEXT NOT NULL, relative_path TEXT NOT NULL, content_hash TEXT NOT NULL,
                created_at TEXT NOT NULL, UNIQUE(asset_id, role, content_hash)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
                stage TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS state_events (
                id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
                from_status TEXT, to_status TEXT NOT NULL, actor TEXT NOT NULL,
                reason TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS exports (
                id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id),
                content_hash TEXT NOT NULL, metadata_revision TEXT NOT NULL,
                verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE(asset_id, content_hash, metadata_revision)
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS idx_events_asset ON state_events(asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_exports_asset ON exports(asset_id, verified);
            UPDATE schema_meta SET version = 1;
            """
        )

    def create_asset(self, filename: str, source_hash: str, batch_id: str) -> AssetCreateResult:
        existing = self.connection.execute(
            "SELECT id FROM assets WHERE source_hash = ?", (source_hash,)
        ).fetchone()
        if existing:
            return AssetCreateResult(existing["id"], True)
        now = utc_now()
        self.connection.execute("INSERT OR IGNORE INTO batches(id, created_at) VALUES (?, ?)", (batch_id, now))
        asset_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO assets(id, batch_id, filename, source_hash, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (asset_id, batch_id, filename, source_hash, AssetStatus.PENDING.value, now, now),
        )
        self.connection.commit()
        return AssetCreateResult(asset_id, False)

    def asset_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0])

    def asset_status(self, asset_id: str) -> AssetStatus:
        row = self.connection.execute("SELECT status FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if not row:
            raise KeyError(asset_id)
        return AssetStatus(row["status"])

    def transition_asset(self, asset_id: str, target: AssetStatus, actor: str, reason: str) -> None:
        current = self.asset_status(asset_id)
        if target is AssetStatus.READY:
            verified = self.connection.execute(
                "SELECT 1 FROM exports WHERE asset_id = ? AND verified = 1 LIMIT 1", (asset_id,)
            ).fetchone()
            if not verified:
                raise InvalidTransition("READY requires a verified export")
        transition(current, target, actor=actor)
        now = utc_now()
        self.connection.execute(
            "UPDATE assets SET status = ?, version = version + 1, updated_at = ? WHERE id = ?",
            (target.value, now, asset_id),
        )
        self.connection.execute(
            "INSERT INTO state_events(id, asset_id, from_status, to_status, actor, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), asset_id, current.value, target.value, actor, reason, now),
        )
        self.connection.commit()

    def add_verified_export(self, asset_id: str, content_hash: str, metadata_revision: str) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO exports(id, asset_id, content_hash, metadata_revision, verified, created_at) VALUES (?, ?, ?, ?, 1, ?)",
            (str(uuid4()), asset_id, content_hash, metadata_revision, utc_now()),
        )
        self.connection.commit()

    def enqueue_job(self, asset_id: str, stage: str, input_hash: str) -> str:
        job_id = str(uuid4())
        self.connection.execute(
            "INSERT INTO jobs(id, asset_id, stage, state, attempt, created_at) VALUES (?, ?, ?, 'QUEUED', 1, ?)",
            (job_id, asset_id, stage, utc_now()),
        )
        self.connection.commit()
        return job_id

    def claim_next_job(self, stage: str, worker_id: str) -> sqlite3.Row | None:
        """Claim one queued job transactionally; SQLite serializes this short claim."""
        self.connection.execute("BEGIN IMMEDIATE")
        job = self.connection.execute(
            "SELECT * FROM jobs WHERE stage = ? AND state = 'QUEUED' ORDER BY created_at LIMIT 1",
            (stage,),
        ).fetchone()
        if not job:
            self.connection.commit()
            return None
        self.connection.execute(
            "UPDATE jobs SET state = 'RUNNING' WHERE id = ? AND state = 'QUEUED'", (job["id"],)
        )
        self.connection.commit()
        return self.connection.execute("SELECT * FROM jobs WHERE id = ?", (job["id"],)).fetchone()

    def finish_job(self, job_id: str, succeeded: bool) -> None:
        state = "SUCCEEDED" if succeeded else "FAILED_RETRYABLE"
        self.connection.execute("UPDATE jobs SET state = ? WHERE id = ?", (state, job_id))
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()