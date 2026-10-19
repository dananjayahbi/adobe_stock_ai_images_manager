"""Lifecycle state transitions and derived flags for image records.

``ImageLifecycleState`` (the ``state`` column) is the single coordinate the
publish/download/export flow reads. Everything else it needs is *derived*:

* ``compute_flags`` — the badge list the UI shows, recomputed from the stored
  columns on every serialization (flags are never written to the database).
* ``refresh_state_for_stage`` — maps a stage transition onto the state axis
  without ever clobbering the operator's manual states.

Sticky-state rules (documented in one place so every caller agrees):

* ``READY_TO_PUBLISH`` survives any pipeline re-run — it only drops to
  ``REJECTED`` when the pipeline fails, so a queued record that fails review
  leaves the publish queue instead of silently uploading a rejected image.
* ``PUBLISHED`` and ``AS_ACCEPTED`` are never recomputed from the stage; the
  publish action and the ``PATCH /state`` endpoint are the only writers.
"""

from __future__ import annotations

from models import ImageLifecycleState, ImageRecord, PipelineStage

#: Stages whose outcome is a pipeline rejection.
REJECTED_STAGES: frozenset[PipelineStage] = frozenset(
    {
        PipelineStage.OCR_REJECTED,
        PipelineStage.INCOMPATIBLE,
        PipelineStage.QUARANTINED,
    }
)

#: States that may enter the Adobe download/export/publish flow.
DELIVERABLE_STATES: frozenset[ImageLifecycleState] = frozenset(
    {
        ImageLifecycleState.READY_TO_PUBLISH,
        ImageLifecycleState.PUBLISHED,
        ImageLifecycleState.AS_ACCEPTED,
    }
)

#: Manual ``PATCH /api/records/{id}/state`` whitelist: from-state -> to-states.
ALLOWED_STATE_TRANSITIONS: dict[
    ImageLifecycleState, frozenset[ImageLifecycleState]
] = {
    # APPROVED -> REJECTED is the detail page's manual Reject button.
    ImageLifecycleState.APPROVED: frozenset(
        {ImageLifecycleState.READY_TO_PUBLISH, ImageLifecycleState.REJECTED}
    ),
    ImageLifecycleState.REJECTED: frozenset(
        {ImageLifecycleState.READY_TO_PUBLISH, ImageLifecycleState.APPROVED}
    ),
    ImageLifecycleState.READY_TO_PUBLISH: frozenset({ImageLifecycleState.APPROVED}),
    ImageLifecycleState.PUBLISHED: frozenset({ImageLifecycleState.AS_ACCEPTED}),
    ImageLifecycleState.AS_ACCEPTED: frozenset({ImageLifecycleState.PUBLISHED}),
}


def state_for_stage(stage: PipelineStage) -> ImageLifecycleState:
    """The stage-derived lifecycle state, ignoring the record's current one.

    Only the values ``refresh_state_for_stage`` is allowed to move between:
    REJECTED for terminal failures, APPROVED for a passed+named record,
    PUBLISHED once staged, COLLECTED everywhere else (mid-pipeline).
    """
    if stage in REJECTED_STAGES:
        return ImageLifecycleState.REJECTED
    if stage == PipelineStage.METADATA_READY:
        return ImageLifecycleState.APPROVED
    if stage == PipelineStage.PUBLISHED:
        return ImageLifecycleState.PUBLISHED
    return ImageLifecycleState.COLLECTED


def refresh_state_for_stage(record: ImageRecord) -> None:
    """Recompute ``record.state`` after a stage transition, respecting stickiness.

    Only ``COLLECTED``/``APPROVED``/``REJECTED`` track the stage. A queued
    (``READY_TO_PUBLISH``) record keeps its place unless the pipeline failed
    (the one derived move it may make). ``PUBLISHED``/``AS_ACCEPTED`` are never
    touched here — the publish action and the manual state endpoint own them.
    """
    if record.state in (
        ImageLifecycleState.PUBLISHED,
        ImageLifecycleState.AS_ACCEPTED,
    ):
        return

    derived = state_for_stage(record.stage)
    if record.state == ImageLifecycleState.READY_TO_PUBLISH:
        # Sticky except to REJECTED: a queued record that fails review must
        # leave the queue, but a successful re-run never revokes the queueing.
        if derived == ImageLifecycleState.REJECTED:
            record.state = derived
        return

    record.state = derived


def apply_state_change(record: ImageRecord, target: ImageLifecycleState) -> bool:
    """Apply a manual state change if the whitelist allows it.

    Returns True when the record was moved, False when the transition is not
    in ``ALLOWED_STATE_TRANSITIONS`` (same-state moves included).
    """
    allowed = ALLOWED_STATE_TRANSITIONS.get(record.state, frozenset())
    if target not in allowed:
        return False
    record.state = target
    return True


def push_state_for_used(record: ImageRecord) -> None:
    """Marking a record used implies it was published — unless Adobe already accepted it."""
    if record.state != ImageLifecycleState.AS_ACCEPTED:
        record.state = ImageLifecycleState.PUBLISHED


def compute_flags(record: ImageRecord) -> list[str]:
    """Derive the record's flag badges, in display order.

    Exactly one of ``USED``/``UNUSED`` is always present; the rest appear only
    when their evidence does. Stickiness prefers the ``stage_details`` blob so a
    stage reset cannot silently drop a rejection that really happened.
    """
    details = record.stage_details or {}
    flags: list[str] = []

    # 1. QUARANTINED — terminal stage, or a stored *rejection* decision. The
    #    gate also writes its blob for records it kept, so `keep` is what
    #    separates "quarantined" from "merely scored".
    diversity_gate = details.get("diversity_gate")
    if record.stage == PipelineStage.QUARANTINED or (
        isinstance(diversity_gate, dict) and not diversity_gate.get("keep", False)
    ):
        flags.append("QUARANTINED")

    # 2. USED / UNUSED — never stored; the complement keeps exactly one present.
    flags.append("USED" if record.is_used else "UNUSED")

    # 3. METADATA_READY — a stored generation, or the title it produced.
    if details.get("metadata") or (record.generated_title or "").strip():
        flags.append("METADATA_READY")

    # 4. INCOMPATIBLE — terminal stage, or a stored failed verdict.
    compatibility = details.get("compatibility")
    if record.stage == PipelineStage.INCOMPATIBLE or (
        isinstance(compatibility, dict) and compatibility.get("passed") is False
    ):
        flags.append("INCOMPATIBLE")

    # 5. REFINED — at least one automatic refine pass ran.
    if (record.refine_passes or 0) > 0:
        flags.append("REFINED")

    # 6. UPSCALED — an upscale step recorded its run.
    if details.get("upscale"):
        flags.append("UPSCALED")

    # 7. OCR_REJECTED — terminal stage, or a stored blocked scan.
    ocr = details.get("ocr")
    if record.stage == PipelineStage.OCR_REJECTED or (
        isinstance(ocr, dict) and ocr.get("blocked")
    ):
        flags.append("OCR_REJECTED")

    return flags
