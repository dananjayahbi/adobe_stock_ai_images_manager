"""Human-supervised lifecycle contract defined by Wave 1."""

from enum import Enum


class AssetStatus(str, Enum):
    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    QUEUED = "QUEUED"
    AUDITING = "AUDITING"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PASSED_FOR_REVIEW = "PASSED_FOR_REVIEW"
    PASSED = "PASSED"
    FLAGGED = "FLAGGED"
    APPROVED = "APPROVED"
    FINALIZING = "FINALIZING"
    FINALIZATION_FAILED = "FINALIZATION_FAILED"
    READY = "READY"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class InvalidTransition(ValueError):
    """Raised when an action violates the human-in-the-loop lifecycle."""


_TRANSITIONS: dict[AssetStatus, frozenset[AssetStatus]] = {
    AssetStatus.PENDING: frozenset({AssetStatus.VALIDATING, AssetStatus.REJECTED}),
    AssetStatus.VALIDATING: frozenset({AssetStatus.QUEUED, AssetStatus.REVIEW_REQUIRED, AssetStatus.FAILED}),
    AssetStatus.QUEUED: frozenset({AssetStatus.AUDITING, AssetStatus.FAILED}),
    AssetStatus.AUDITING: frozenset({AssetStatus.REVIEW_REQUIRED, AssetStatus.PASSED_FOR_REVIEW, AssetStatus.FAILED}),
    AssetStatus.REVIEW_REQUIRED: frozenset({AssetStatus.APPROVED, AssetStatus.REJECTED, AssetStatus.AUDITING}),
    AssetStatus.PASSED_FOR_REVIEW: frozenset({AssetStatus.APPROVED, AssetStatus.REJECTED, AssetStatus.AUDITING}),
    AssetStatus.PASSED: frozenset({AssetStatus.APPROVED, AssetStatus.FLAGGED, AssetStatus.REJECTED, AssetStatus.AUDITING}),
    AssetStatus.FLAGGED: frozenset({AssetStatus.APPROVED, AssetStatus.REJECTED, AssetStatus.AUDITING}),
    AssetStatus.APPROVED: frozenset({AssetStatus.FINALIZING, AssetStatus.FINALIZATION_FAILED, AssetStatus.REJECTED}),
    AssetStatus.FINALIZING: frozenset({AssetStatus.READY, AssetStatus.FINALIZATION_FAILED}),
    AssetStatus.FINALIZATION_FAILED: frozenset({AssetStatus.APPROVED, AssetStatus.REJECTED}),
    AssetStatus.READY: frozenset({AssetStatus.AUDITING, AssetStatus.REJECTED}),
    AssetStatus.FAILED: frozenset({AssetStatus.VALIDATING, AssetStatus.AUDITING, AssetStatus.REJECTED}),
    AssetStatus.REJECTED: frozenset({AssetStatus.VALIDATING, AssetStatus.AUDITING}),
}


def transition(current: AssetStatus, target: AssetStatus, *, actor: str) -> AssetStatus:
    if not actor.strip():
        raise InvalidTransition("Every transition requires an attributable local actor.")
    if target not in _TRANSITIONS[current]:
        raise InvalidTransition(f"Cannot transition {current.value} to {target.value}.")
    if target is AssetStatus.READY and current is not AssetStatus.FINALIZING:
        raise InvalidTransition("Only a verified finalization can become READY.")
    return target