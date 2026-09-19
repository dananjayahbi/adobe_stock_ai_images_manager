"""Auto-fix API.

One endpoint, deliberately synchronous: fixing a single image is a
sub-second-to-few-second operation, and the operator is watching the modal while
it happens. Making it a background job would add polling machinery for no gain
and would leave the modal showing a stale report.

The record's stage is left untouched. An auto-fix is a *correction attempt*, not
a pipeline transition - the operator decides whether to re-run the compatibility
check afterwards, and re-running is what moves the record.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import ImageRecord, utcnow
from schemas import AutoFixResponse
from services import autofix
from services.acceptance.scorer import AcceptanceConfig

logger = logging.getLogger(__name__)

router = APIRouter(tags=["autofix"])

#: Working-file variants an auto-fix may correct. Deliberately limited: fixing
#: the untouched original would discard the pipeline's own history.
VALID_VARIANTS = frozenset({"working", "refined", "upscaled"})

#: Correction modes. ``single`` applies the recipe once; ``adaptive`` escalates
#: across repeated passes until the per-dimension target is met.
VALID_MODES = frozenset({"single", "adaptive"})


def _progress_dict(result, attribute: str) -> dict | None:
    """Serialise a TargetProgress attribute when the result carries one."""
    progress = getattr(result, attribute, None)
    return progress.to_dict() if progress is not None else None


def _resolve_source(record: ImageRecord, variant: str):
    """Pick the file to correct for a given variant request."""
    if variant == "refined":
        candidate = settings.REFINED_DIR / f"{record.id}-refined.jpg"
    elif variant == "upscaled":
        candidate = settings.UPSCALED_DIR / f"{record.id}-upscaled.jpg"
    else:
        candidate = record.working_path or record.original_path

    from pathlib import Path

    path = Path(candidate) if candidate else None
    if path and path.is_file():
        return path

    # Fall back to whatever the pipeline would use, so a missing intermediate
    # (a record never refined, say) does not fail the request outright.
    from tasks.stage_orchestrator import _current_path

    fallback = _current_path(record)
    if fallback.is_file():
        return fallback
    raise HTTPException(
        status_code=404,
        detail="No readable working file exists for this record.",
    )


@router.post("/api/records/{record_id}/autofix", response_model=AutoFixResponse)
async def auto_fix_record(
    record_id: str,
    variant: str = "working",
    mode: str = "single",
    target: float | None = None,
    db: Session = Depends(get_db),
) -> AutoFixResponse:
    """Apply automatically fixable corrections and re-score the image.

    Two modes:

    * ``single`` (default) - one pass of the corrective recipe. Fast, and the
      right choice when the image is close to compliant.
    * ``adaptive`` - repeat with escalating correction strength until every
      auto-fixable score dimension reaches ``target``, recording a decision log.
      This is the mode that can actually move the acceptance score, because the
      single-pass recipe recomputes identical strengths and is therefore
      idempotent.

    The corrected file becomes the record's working copy and the fresh report
    replaces the stale one. **The record's stage is never changed** - an auto-fix
    is a correction attempt, not a pipeline transition; the operator decides
    whether to re-run the compatibility check.
    """
    if variant not in VALID_VARIANTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown variant '{variant}'. Use one of: {', '.join(sorted(VALID_VARIANTS))}.",
        )
    if mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode '{mode}'. Use one of: {', '.join(sorted(VALID_MODES))}.",
        )

    record = db.query(ImageRecord).filter(ImageRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} does not exist.")

    source = _resolve_source(record, variant)

    # Reuse the semantic audit already on file rather than calling the LLM
    # again: the operator asked to fix pixels, not to re-litigate the semantic
    # verdict, and a second call would double the wait for no new information.
    semantic = _semantic_from_record(record)

    if mode == "adaptive":
        result = autofix.auto_fix_adaptive(
            source,
            settings.REFINED_DIR,
            record.id,
            target=target,
            semantic=semantic,
            settings=settings,
            config=AcceptanceConfig.from_settings(),
        )
    else:
        result = autofix.auto_fix_image(
            source,
            settings.REFINED_DIR,
            record.id,
            semantic=semantic,
            settings=settings,
            config=AcceptanceConfig.from_settings(),
        )

    if not result.success:
        raise HTTPException(
            status_code=422,
            detail=result.reason or "The automatic fix could not be applied.",
        )

    record.working_path = result.output_path
    record.acceptance_report = result.report.to_dict() if result.report else None
    record.acceptance_score = result.final_score
    details = dict(record.stage_details or {})
    details["autofix"] = result.to_dict()
    record.stage_details = details
    record.stage_updated_at = utcnow()
    # NOTE: `record.stage` and `record.queued_stage` are deliberately NOT touched.
    # An auto-fix is a correction attempt, not a pipeline transition. Moving the
    # record here would silently promote an image the operator has not reviewed,
    # and would make the "re-run the compatibility check" decision for them.
    # `test_autofix_never_moves_the_record_between_stages` guards this.
    db.commit()
    db.refresh(record)

    return AutoFixResponse(
        record_id=record.id,
        mode=mode,
        fixed=result.fixed,
        remaining_fixable=result.remaining_fixable,
        manual=result.manual,
        passes=result.passes,
        initial_score=result.initial_score,
        final_score=result.final_score,
        improved=result.improved,
        initial_passed=result.initial_passed,
        final_passed=result.final_passed,
        srgb_embedded=result.srgb_embedded,
        history=result.history,
        summary=_summarise(result),
        # Only the adaptive loop has a stop reason. Single mode runs the recipe
        # once and has nothing to explain, so falling back to `reason` here would
        # put a score summary in a field the UI labels "why it stopped".
        stop_reason=getattr(result, "stop_reason", ""),
        target=getattr(result, "target", None),
        target_met=bool(getattr(result, "target_met", False)),
        log=getattr(result, "log", []),
        progress_before=_progress_dict(result, "progress_before"),
        progress_after=_progress_dict(result, "progress_after"),
        record=record,
    )


def _semantic_from_record(record: ImageRecord) -> dict | None:
    """Rebuild the semantic audit dict persisted by Stage 5, when present."""
    if record.semantic_confidence_score is None and not record.semantic_flags:
        return None
    return {
        "confidence_score": record.semantic_confidence_score,
        "flags": list(record.semantic_flags or []),
    }


def _summarise(result) -> str:
    """One-line, operator-facing description of what the fix achieved."""
    stop_reason = getattr(result, "stop_reason", "") or result.reason

    if result.final_passed and not result.initial_passed:
        return (
            f"Fixed {len(result.fixed)} issue type(s) - now passes at "
            f"{result.final_score * 100:.1f}%."
        )
    if result.improved:
        remaining = len(result.manual) + len(result.remaining_fixable)
        return (
            f"Score improved {result.initial_score * 100:.1f}% → "
            f"{result.final_score * 100:.1f}%. {remaining} issue(s) still need "
            "attention."
        )
    # No movement: the reason matters far more than the counts, because the
    # usual cause is a cap the engine cannot touch (a critical issue or a
    # dimension scoring zero), not a failed correction.
    return (
        f"No score change from {len(result.fixed)} fix(es). {stop_reason} "
        f"{len(result.manual)} issue(s) need a manual decision."
    ).strip()
