"""Manual promotion of records to the ready-to-upload (Stage 6) state.

The gallery lets the operator select images — including terminal ones such as
QUARANTINED — and push them to ``METADATA_READY``. That move is deliberately
*not* a bare stage flip: an image may only land there when the three
deliverable requirements hold:

1. **Acceptance QC**   - a passing acceptance report (Stage 5 gate).
2. **Embedded sRGB**   - the working file carries an sRGB ICC profile.
3. **Metadata & keywords** - title/description/keywords/category exist.

``evaluate_record`` reports which of those already hold so the UI can show the
mismatch list *before* anything runs; ``run_missing_steps`` then executes only
the gaps, per record. Both are synchronous single-record helpers so the batch
driver (``tasks/promote_orchestrator``) stays a thin loop.
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from config import Settings
from models import ImageRecord, ImageStatus, PipelineStage, utcnow
from services import (
    compatibility_checker,
    gemini_metadata,
    prompt_context,
    record_metrics,
)
from services.acceptance.scorer import AcceptanceConfig
from services.srgb_profile import ensure_srgb_profile, has_srgb_profile

logger = logging.getLogger(__name__)

#: Stable step keys shared with the frontend's promote dialog.
STEP_ACCEPTANCE = "acceptance"
STEP_SRGB = "srgb"
STEP_METADATA = "metadata"

#: Operator-facing labels for the three requirements.
STEP_LABELS: dict[str, str] = {
    STEP_ACCEPTANCE: "Acceptance QC",
    STEP_SRGB: "Embedded sRGB profile",
    STEP_METADATA: "Metadata & keywords",
}

#: Stages that must not be promoted. OCR_REJECTED is a content-policy
#: violation (embedded text), not a quality judgement, so unlike the diversity
#: quarantine it is never overridden by hand.
INELIGIBLE_STAGES: frozenset[PipelineStage] = frozenset({PipelineStage.OCR_REJECTED})


def _current_path(record: ImageRecord) -> Path:
    """The file the promote steps operate on (working copy, else original)."""
    for candidate in (record.working_path, record.original_path):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return Path(record.original_path or "")


def _step(
    key: str,
    ok: bool,
    detail: str,
) -> dict:
    return {
        "key": key,
        "label": STEP_LABELS[key],
        "ok": ok,
        "detail": detail,
    }


def _acceptance_ok(record: ImageRecord) -> bool:
    report = record.acceptance_report or {}
    return bool(report.get("passed"))


def evaluate_record(record: ImageRecord) -> dict:
    """Report which promote requirements already hold for one record.

    Read-only: nothing on disk or in the database is touched. The result
    shapes the pre-flight modal, and its per-step ``ok`` flags are exactly
    what ``run_missing_steps`` uses to decide what to execute.
    """
    eligible = record.stage not in INELIGIBLE_STAGES
    steps: list[dict] = []

    if _acceptance_ok(record):
        score = record.acceptance_score
        detail = (
            f"Passing report ({score:.0%})."
            if score is not None
            else "Passing acceptance report."
        )
        steps.append(_step(STEP_ACCEPTANCE, True, detail))
    elif record.acceptance_report:
        score = record.acceptance_score
        detail = (
            f"Report did not pass ({score:.0%})."
            if score is not None
            else "Report did not pass."
        )
        steps.append(_step(STEP_ACCEPTANCE, False, detail))
    else:
        steps.append(_step(STEP_ACCEPTANCE, False, "No acceptance report yet."))

    source = _current_path(record)
    if not source.is_file():
        steps.append(
            _step(STEP_SRGB, False, "Working file is missing on disk.")
        )
    elif has_srgb_profile(source):
        steps.append(_step(STEP_SRGB, True, "File already carries an sRGB profile."))
    else:
        steps.append(_step(STEP_SRGB, False, "No sRGB ICC profile in the file."))

    title = (record.generated_title or "").strip()
    keyword_count = len(record.generated_keywords or [])
    if title and keyword_count:
        steps.append(
            _step(STEP_METADATA, True, f"Title and {keyword_count} keywords present.")
        )
    elif title or keyword_count:
        missing_bits = []
        if not title:
            missing_bits.append("title")
        if not keyword_count:
            missing_bits.append("keywords")
        steps.append(
            _step(STEP_METADATA, False, f"Missing {' and '.join(missing_bits)}.")
        )
    else:
        steps.append(_step(STEP_METADATA, False, "No metadata generated yet."))

    blocker: str | None = None
    if not eligible:
        blocker = (
            "OCR rejected: embedded text is a content-policy violation and "
            "cannot be promoted."
        )
    elif record.stage == PipelineStage.PUBLISHED:
        blocker = "Already published (staged for upload)."

    return {
        "record_id": record.id,
        "filename": record.filename,
        "stage": record.stage.value,
        "eligible": eligible and blocker is None,
        "blocker": blocker,
        "steps": steps,
    }


def run_missing_steps(
    db: Session,
    record: ImageRecord,
    cfg: Settings,
    *,
    use_semantic: bool = False,
) -> tuple[bool, list[str]]:
    """Run whichever of the three requirements are missing, then promote.

    Returns ``(promoted, messages)``. ``promoted`` is True only when every
    requirement holds at the end; a failure mid-way leaves the record's stage
    untouched (already-produced artifacts such as a fresh acceptance report
    are kept, so a retry skips what succeeded).

    The acceptance QC re-runs the real Stage 5 algorithm — it does not trust a
    stored "passed" alone for the *promotion decision* beyond the cheap check
    in ``evaluate_record``; when the report already passes it is reused.
    """
    messages: list[str] = []
    source = _current_path(record)

    # ---------------------------------------------------------------- 1. QC
    if _acceptance_ok(record):
        messages.append("Acceptance QC: already passing — skipped.")
    else:
        if not source.is_file():
            return False, [f"Working file not found: {source.name or '(none)'}."]

        semantic = None
        if use_semantic:
            from services import gemini_auditor

            semantic = gemini_auditor.audit_image(
                source, api_key=cfg.effective_llm_api_key
            )

        verdict = compatibility_checker.check_compatibility(
            source, semantic=semantic, config=AcceptanceConfig.from_settings()
        )
        record.acceptance_report = verdict.report.to_dict()
        record.acceptance_score = verdict.report.score
        if semantic:
            record.semantic_confidence_score = semantic.get("confidence_score")
            record.semantic_flags = [
                str(flag) for flag in semantic.get("flags", [])
            ] or [issue.detail for issue in verdict.report.issues]

        if not verdict.passed:
            db.commit()  # keep the fresh report so the UI can show why
            return False, [f"Acceptance QC failed: {verdict.summary}"]
        messages.append(f"Acceptance QC: passed ({verdict.report.score:.0%}).")

    # -------------------------------------------------------------- 2. sRGB
    if not source.is_file():
        return False, messages + [f"Working file not found: {source.name or '(none)'}."]

    if has_srgb_profile(source):
        messages.append("sRGB profile: already tagged — skipped.")
    else:
        out_dir = Path(cfg.SRGB_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        destination = out_dir / f"{record.id}-srgb{source.suffix.lower() or '.jpg'}"
        result = ensure_srgb_profile(source, destination)
        if not result.get("ok"):
            db.commit()
            return False, messages + [
                f"sRGB embed failed: {result.get('reason', 'unknown error')}"
            ]

        details = dict(record.stage_details or {})
        details["embed_srgb"] = result
        record.stage_details = details
        if result.get("applied") and result.get("output_path"):
            record.working_path = result["output_path"]
            record_metrics.refresh_delivery_metrics(record, cfg)
            source = _current_path(record)
            messages.append("sRGB profile: embedded.")
        else:
            messages.append("sRGB profile: already tagged — skipped.")

    # ----------------------------------------------------------- 3. Metadata
    title = (record.generated_title or "").strip()
    keywords = record.generated_keywords or []
    if title and keywords:
        messages.append(
            f"Metadata: already present ({len(keywords)} keywords) — skipped."
        )
    else:
        metadata = gemini_metadata.generate_metadata(
            source,
            api_key=cfg.effective_llm_api_key,
            original_filename=record.filename,
            generation_prompt=prompt_context.brief_for(db, record.prompt_id),
        )
        if not metadata:
            db.commit()
            return False, messages + [
                "Metadata generation returned nothing usable."
            ]

        record.generated_title = (metadata.get("title") or "")[:500] or None
        record.generated_description = metadata.get("description") or None
        record.generated_keywords = metadata.get("keywords") or []
        record.category = metadata.get("category")
        record.suggested_filename = metadata.get("suggested_filename") or None
        messages.append(
            f"Metadata: generated "
            f"({len(record.generated_keywords or [])} keywords)."
        )

    # ------------------------------------------------------------ 4. Promote
    if not (record.generated_title or "").strip() or not (record.generated_keywords or []):
        db.commit()
        return False, messages + [
            "Metadata incomplete after generation — not promoted."
        ]

    details = dict(record.stage_details or {})
    details["promote"] = {
        "promoted_at": utcnow().isoformat(),
        "from_stage": record.stage.value,
    }
    record.stage_details = details
    record.stage = PipelineStage.METADATA_READY
    record.queued_stage = None
    record.stage_updated_at = utcnow()
    if record.status != ImageStatus.READY:
        record.status = ImageStatus.PASSED
    db.commit()
    messages.append(f"Promoted to {PipelineStage.METADATA_READY.value}.")
    return True, messages
