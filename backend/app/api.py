"""Versioned local API contracts for Wave 8.

This module deliberately keeps wire schemas independent from SQLite rows and web-framework
objects. A FastAPI adapter can map these contracts to HTTP routes without exposing paths,
secrets, or provider envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
from typing import Any, Iterable, Mapping


class ApiError(ValueError):
    """Safe, client-facing API validation or concurrency error."""


@dataclass(frozen=True)
class CursorPage:
    items: tuple[dict[str, Any], ...]
    next_cursor: str | None
    limit: int


def paginate(records: Iterable[Mapping[str, Any]], *, limit: int = 50, cursor: str | None = None) -> CursorPage:
    if not 1 <= limit <= 100:
        raise ApiError("limit must be between 1 and 100")
    ordered = sorted((dict(record) for record in records), key=lambda record: str(record.get("id", "")))
    start = 0
    if cursor is not None:
        ids = [str(item.get("id", "")) for item in ordered]
        if cursor not in ids:
            raise ApiError("cursor is invalid")
        start = ids.index(cursor) + 1
    selected = ordered[start : start + limit]
    return CursorPage(tuple(selected), str(selected[-1]["id"]) if len(selected) == limit else None, limit)


def validate_action(*, expected_revision: int | None, idempotency_key: str, actor: str) -> None:
    if expected_revision is None or expected_revision < 0:
        raise ApiError("expected revision is required")
    if not idempotency_key.strip() or len(idempotency_key) > 200:
        raise ApiError("idempotency key is required")
    if not actor.strip() or len(actor) > 200:
        raise ApiError("actor is required")


class IdempotencyStore:
    def __init__(self):
        self._records: dict[str, tuple[str, dict[str, Any]]] = {}

    @staticmethod
    def _fingerprint(payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def record(self, key: str, payload: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = self._fingerprint(payload)
        existing = self._records.get(key)
        if existing and existing[0] != fingerprint:
            raise ApiError("idempotency key was used with a different payload")
        if existing:
            return dict(existing[1])
        self._records[key] = (fingerprint, dict(result))
        return dict(result)

    def replay(self, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if key not in self._records:
            raise ApiError("idempotency key was not found")
        fingerprint, result = self._records[key]
        if fingerprint != self._fingerprint(payload):
            raise ApiError("idempotency key was used with a different payload")
        return dict(result)


@dataclass(frozen=True)
class Session:
    session_id: str
    actor: str
    created_at: datetime
    expires_at: datetime


class SessionManager:
    def __init__(self, *, ttl_seconds: int = 3600):
        if not 60 <= ttl_seconds <= 86_400:
            raise ValueError("session TTL must be between 60 seconds and 24 hours")
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, Session] = {}

    def create(self, actor: str) -> Session:
        if not actor.strip():
            raise ApiError("actor is required")
        now = datetime.now(timezone.utc)
        session = Session(secrets.token_urlsafe(24), actor.strip(), now, now + timedelta(seconds=self.ttl_seconds))
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None or session.expires_at <= datetime.now(timezone.utc):
            self._sessions.pop(session_id, None)
            raise ApiError("session is expired or invalid")
        return session

    def expire(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def safe_asset_response(asset: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"id", "status", "version", "batch_id", "filename", "updated_at"}
    response = {key: asset[key] for key in allowed if key in asset}
    findings = asset.get("findings")
    response["findings"] = list(findings[:25]) if isinstance(findings, list) and all(isinstance(item, Mapping) for item in findings) else []
    return response


@dataclass(frozen=True)
class JobSnapshot:
    job_id: str
    asset_id: str | None
    operation: str
    status: str
    stage: str
    completed: int
    total: int
    failed: int
    blocked: int
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.job_id,
            "asset_id": self.asset_id,
            "operation": self.operation,
            "status": self.status,
            "stage": self.stage,
            "progress": {"completed": self.completed, "total": self.total, "failed": self.failed, "blocked": self.blocked},
            "error": self.error,
        }


def create_error(error_type: str, code: str, message: str, *, correlation_id: str) -> dict[str, str]:
    if not all(isinstance(value, str) and value.strip() for value in (error_type, code, message, correlation_id)):
        raise ApiError("error envelope fields are required")
    return {"type": error_type, "code": code, "message": message[:500], "correlation_id": correlation_id}
