"""Stable, safe error contracts for API and operational boundaries."""

from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    USER_CORRECTABLE = "user_correctable"
    RETRYABLE = "retryable"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    TERMINAL_ASSET = "terminal_asset"
    INTERNAL = "internal"


@dataclass
class StudioError(Exception):
    category: ErrorCategory
    code: str
    message: str
    stage: str
    correlation_id: str
    detail: str | None = None
    attempt: int = 1

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, object]:
        """Return the safe envelope; internal detail is intentionally omitted."""
        return {
            "category": self.category.value,
            "code": self.code,
            "message": self.message,
            "stage": self.stage,
            "attempt": self.attempt,
            "correlation_id": self.correlation_id,
        }
