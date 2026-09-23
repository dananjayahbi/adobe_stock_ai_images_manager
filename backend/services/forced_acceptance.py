"""Forced acceptance - the operator's manual override of a pipeline verdict.

The compatibility gate is a *heuristic*, and the acceptance score is explicitly a
ranking signal rather than a verdict (reviewer variance exceeds any threshold's
resolution). There are therefore real cases where the operator knows better than
the scorer: a deliberately soft-focus image, a genuinely minimal composition, a
measured resolution the scorer mis-read.

Without an override those images were dead ends - the only way forward was to
edit the database by hand. This module is the supported path. It is deliberately
*not* a threshold change: the stored score and report are left exactly as the
scorer produced them, so the record still shows the honest measurement and the
override is visible as a separate, attributed decision.

Two things are always recorded, because an override that leaves no trace is
indistinguishable from a bug in the gate:

* ``stage_details["forced"]`` - who/why/when, plus the score that was overridden,
* ``semantic_flags`` keeps the original reasons, so the UI can still show *why*
  the scorer objected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from models import ImageRecord, PipelineStage, utcnow

logger = logging.getLogger(__name__)

#: The stages a record may be forced *out of*.
#:
#: Deliberately excludes ``OCR_REJECTED``: embedded text is a hard content-policy
#: problem, not a quality judgement, so it is not the operator's to waive. It also
#: excludes the already-passing stages, where there is nothing to override.
FORCEABLE_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PipelineStage.INCOMPATIBLE,
        PipelineStage.COLLECTED,
        PipelineStage.OCR_CLEAR,
        PipelineStage.UPSCALED,
        PipelineStage.REFINED,
    }
)

#: Longest reason stored, so a pasted essay cannot bloat the JSON column.
MAX_REASON_LENGTH = 500


@dataclass
class ForcedAcceptanceResult:
    """Outcome of one forced-acceptance attempt."""

    record_id: str
    accepted: bool
    previous_stage: str
    new_stage: str | None = None
    score: float | None = None
    reason: str = ""


def can_force(record: ImageRecord) -> tuple[bool, str]:
    """Whether this record may be force-accepted, and why not if it may not.

    Returning the reason (rather than just a bool) lets the API report a
    per-record explanation in a bulk run instead of a bare "skipped".
    """
    if record.stage == PipelineStage.PUBLISHED:
        return False, "Already published."
    if record.stage == PipelineStage.METADATA_READY:
        return False, "Already accepted (metadata is ready)."
    if record.stage == PipelineStage.OCR_REJECTED:
        return False, (
            "Embedded text was detected. That is a content-policy rejection, not a "
            "quality judgement, so it cannot be force-accepted."
        )
    if record.stage == PipelineStage.INCOMPATIBLE:
        return True, ""
    if record.stage in FORCEABLE_STAGES:
        # A record still earlier in the pipeline can be forced forward too: the
        # operator may be bypassing a gate they consider irrelevant.
        return True, ""
    return False, f"Stage {record.stage.value} cannot be force-accepted."


def force_accept(
    record: ImageRecord,
    *,
    reason: str = "",
    target: PipelineStage = PipelineStage.COMPATIBLE,
) -> ForcedAcceptanceResult:
    """Advance a record past the acceptance gate, recording the override.

    The score and the acceptance report are **preserved**. That is the point of
    the override: the measurement stays honest and the decision to proceed
    despite it is recorded alongside, rather than the number being quietly
    rewritten to look like a pass.

    The caller owns the commit, so a bulk run can commit once.
    """
    previous = record.stage
    ok, why = can_force(record)
    if not ok:
        return ForcedAcceptanceResult(
            record_id=record.id,
            accepted=False,
            previous_stage=previous.value,
            score=record.acceptance_score,
            reason=why,
        )

    cleaned_reason = (reason or "").strip()[:MAX_REASON_LENGTH]

    details = dict(record.stage_details or {})
    # Preserve any earlier override rather than overwriting the audit trail.
    history = list(details.get("forced_history") or [])
    history.append(
        {
            "at": utcnow().isoformat(),
            "from": previous.value,
            "score": record.acceptance_score,
            "reason": cleaned_reason,
        }
    )

    details["forced"] = {
        "at": utcnow().isoformat(),
        "from": previous.value,
        "score": record.acceptance_score,
        "reason": cleaned_reason,
        # The scorer's own objections are kept so the UI can still explain the
        # measurement that was overridden.
        "issues": [
            issue.get("code")
            for issue in ((record.acceptance_report or {}).get("issues") or [])
            if isinstance(issue, dict)
        ],
    }
    details["forced_history"] = history
    record.stage_details = details

    record.stage = target
    record.stage_updated_at = utcnow()
    # The queue entry for the stage we just satisfied is stale.
    record.queued_stage = None

    logger.info(
        "Record %s force-accepted from %s (score %s): %s",
        record.id,
        previous.value,
        record.acceptance_score,
        cleaned_reason or "no reason given",
    )

    return ForcedAcceptanceResult(
        record_id=record.id,
        accepted=True,
        previous_stage=previous.value,
        new_stage=target.value,
        score=record.acceptance_score,
        reason=cleaned_reason,
    )


def forced_detail(record: ImageRecord) -> dict | None:
    """The stored override record, for the API to surface in the UI."""
    details = record.stage_details or {}
    forced = details.get("forced")
    return forced if isinstance(forced, dict) else None


def is_forced(record: ImageRecord) -> bool:
    """True when this record's current position came from an override."""
    return forced_detail(record) is not None
