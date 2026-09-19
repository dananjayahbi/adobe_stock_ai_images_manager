"""The adaptive auto-fix loop.

Why this exists, in one sentence: the single-shot fix was *idempotent*, so
running it repeatedly could never change anything.

The recipe computes each correction's strength as a pure function of the measured
issue and then clamps it to ``MAX_CORRECTION_STRENGTH``. Re-running it on its own
output therefore recomputes the same strengths and produces a byte-identical
image - which is why the first auto-fix reported "fixed 4 issue type(s)" while
the score stayed at 55.0%. The score was in fact pinned by two structural caps:

* ``ceiling_floor`` (0.55) - the worst-dimension ceiling, which holds the total at
  0.55 whenever a dimension scores 0.0; and
* ``threshold - critical_cap_margin`` (0.75) - applied whenever any critical issue
  is present.

Neither can be moved by pixel edits alone. A critical issue such as a 1.1 MP
frame below Adobe's 4 MP floor is *not* auto-fixable, so the honest outcome is
"the engine did its part; something else is blocking you" - which this loop
reports explicitly instead of pretending success.

The loop's actual job is therefore to drive the dimensions the engine *can*
control past the operator's target, escalating the correction strength on each
retry so progress is real rather than nominal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from config import Settings, settings as default_settings
from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import AcceptanceReport
from services.autofix.container import apply_container_fixes
from services.autofix.run_log import RunLog
from services.autofix.targets import (
    DEFAULT_TARGET,
    TargetProgress,
    clamp_target,
    diagnose_stuck,
    dimensions_from_report,
)
from services.refine.recipe import apply_recipe
from services.srgb_profile import has_srgb_profile, write_srgb_jpeg

logger = logging.getLogger(__name__)

#: Hard stop on loop iterations. Each pass writes and re-scores a full-resolution
#: JPEG, so this bounds the worst-case run time.
MAX_ADAPTIVE_PASSES = 12

#: Strength multiplier applied per retry. Deliberately gentle: the point is to
#: make measurable progress, not to reach the cap in two passes.
ESCALATION_STEP = 1.35

#: Smallest score gain that counts as progress. Below this the loop is burning
#: passes on noise, so it stops and reports the plateau.
MIN_MEANINGFUL_GAIN = 0.002


@dataclass
class AdaptiveResult:
    """Outcome of an adaptive auto-fix run."""

    success: bool
    output_path: str | None = None
    passes: int = 0
    initial_score: float = 0.0
    final_score: float = 0.0
    initial_passed: bool = False
    final_passed: bool = False
    target: float = DEFAULT_TARGET
    #: Per-dimension goal tracking, before and after the run.
    progress_before: TargetProgress | None = None
    progress_after: TargetProgress | None = None
    #: Issue codes resolved, judged by measurement movement.
    fixed: list[str] = field(default_factory=list)
    #: Codes still auto-fixable at the end (a further run might help).
    remaining_fixable: list[str] = field(default_factory=list)
    #: Codes only a human can resolve.
    manual: list[str] = field(default_factory=list)
    #: Why the loop stopped - the single most useful thing to tell the operator.
    stop_reason: str = ""
    srgb_embedded: bool = False
    #: Per-pass summary (operations applied and the score each achieved). Kept in
    #: the same shape as the single-pass result so callers can treat both alike.
    history: list[dict] = field(default_factory=list)
    #: The full decision log.
    log: list[dict] = field(default_factory=list)
    report: AcceptanceReport | None = None

    @property
    def improved(self) -> bool:
        return self.final_score > self.initial_score

    @property
    def target_met(self) -> bool:
        return bool(self.progress_after and self.progress_after.all_met)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output_path": self.output_path,
            "passes": self.passes,
            "initial_score": round(self.initial_score, 4),
            "final_score": round(self.final_score, 4),
            "improved": self.improved,
            "initial_passed": self.initial_passed,
            "final_passed": self.final_passed,
            "target": round(self.target, 4),
            "target_met": self.target_met,
            "stop_reason": self.stop_reason,
            "progress_before": (
                self.progress_before.to_dict() if self.progress_before else None
            ),
            "progress_after": (
                self.progress_after.to_dict() if self.progress_after else None
            ),
            "fixed": self.fixed,
            "remaining_fixable": self.remaining_fixable,
            "manual": self.manual,
            "srgb_embedded": self.srgb_embedded,
            "history": self.history,
            "log": self.log,
            "report": self.report.to_dict() if self.report else None,
        }


def _progress(report: AcceptanceReport, target: float) -> TargetProgress:
    return TargetProgress(
        target=target,
        overall_score=report.score,
        dimensions=dimensions_from_report(report),
    )


def _describe_progress(progress: TargetProgress) -> str:
    """Compact per-dimension summary for the log."""
    parts = []
    for dim in progress.dimensions:
        marker = "ok" if dim.met(progress.target) else ("fixable" if dim.is_fixable else "manual")
        parts.append(f"{dim.label} {dim.score * 100:.0f}% ({marker})")
    return "; ".join(parts)


def auto_fix_adaptive(
    file_path: str | Path,
    output_dir: Path | str,
    record_id: str,
    *,
    target: float | None = None,
    semantic: dict | None = None,
    settings: Settings | None = None,
    config: AcceptanceConfig | None = None,
    max_passes: int = MAX_ADAPTIVE_PASSES,
) -> AdaptiveResult:
    """Correct an image repeatedly until its fixable dimensions reach ``target``.

    Args:
        file_path: Image to correct (never modified in place).
        output_dir: Directory receiving the corrected copy.
        record_id: Names the output deterministically, as Stage 4 does.
        target: Per-dimension goal, 0-1. Clamped to the supported range.
        semantic: Optional LLM audit dict, carried into every re-score.
        settings: Application settings override.
        config: Acceptance thresholds override.
        max_passes: Hard iteration cap.

    Returns:
        An :class:`AdaptiveResult` whose ``log`` explains every decision and whose
        ``stop_reason`` states why the loop ended.
    """
    cfg_settings = settings or default_settings
    cfg = config or AcceptanceConfig.from_settings()
    quality = int(getattr(cfg_settings, "EXPORT_JPEG_QUALITY", 95))
    goal = clamp_target(target)
    log = RunLog()

    source = Path(file_path)
    if not source.exists():
        return AdaptiveResult(
            success=False, target=goal, stop_reason=f"File not found: {file_path}"
        )

    report = score_image(source, config=cfg, semantic=semantic)
    initial_score = report.score
    progress = _progress(report, goal)

    log.info(
        f"Starting adaptive auto-fix on {source.name}.",
        score=initial_score,
    )
    log.info(
        f"Target: {goal * 100:.0f}% per dimension. Overall score "
        f"{initial_score * 100:.1f}% (Adobe threshold {cfg.threshold * 100:.0f}%).",
        score=initial_score,
    )
    log.info(f"Dimensions at start - {_describe_progress(progress)}", score=initial_score)

    # ---- Container fixes first: the colour profile decides how the pixel
    # corrections are interpreted, so converting afterwards would apply them in
    # the wrong space.
    container = apply_container_fixes(source, report.issues)
    if container.image_bgr is None:
        return AdaptiveResult(
            success=False,
            target=goal,
            initial_score=initial_score,
            stop_reason="Could not decode the image.",
            log=log.to_list(),
        )

    working = container.image_bgr
    attempted: set[str] = set(container.addressed)
    if container.addressed:
        log.change(
            f"Container fix: {', '.join(container.addressed)}. "
            + (container.notes[0] if container.notes else ""),
            score=initial_score,
        )

    destination = Path(output_dir) / f"{record_id}-refined.jpg"

    # The container fix alone may already satisfy the goal.
    if container.changed:
        if not write_srgb_jpeg(working, destination, quality):
            return AdaptiveResult(
                success=False,
                target=goal,
                initial_score=initial_score,
                stop_reason="Failed to write the corrected image.",
                log=log.to_list(),
            )
        report = score_image(destination, config=cfg, semantic=semantic)
        progress = _progress(report, goal)

    passes = 0
    escalation = 1.0
    previous_score = report.score
    stop_reason = ""
    #: Best (image, report, progress) seen so far. The loop keeps this rather
    #: than the last state, because escalating a correction can make things
    #: *worse* - a stronger defringe was measured pushing the fringe ratio from
    #: 0.213 up to 0.219. The operator must never receive a file that scores
    #: below one the engine already had.
    best = (working, report, progress)

    for pass_number in range(1, max(1, max_passes) + 1):
        pending = progress.unmet_fixable
        if not pending:
            stop_reason = (
                "Every fixable dimension reached the target."
                if not progress.unmet_manual
                else "No auto-fixable dimensions remain below the target."
            )
            break

        targets = ", ".join(f"{d.label} {d.score * 100:.0f}%" for d in pending)
        log.info(
            f"Pass {pass_number}: targeting {targets} "
            f"(escalation ×{escalation:.2f}).",
            pass_number=pass_number,
            score=report.score,
        )

        # Only correct the dimensions that are actually short. Re-applying a
        # correction to a dimension already at target would spend the
        # desaturation budget and risk pushing a good metric out of range.
        target_codes = {code for dim in pending for code in dim.fixable_codes}
        issues = [i for i in report.refinable_issues if i.code in target_codes]
        if not issues:
            stop_reason = "The remaining shortfalls have no pixel-level correction."
            break

        outcome = apply_recipe(
            working, issues, metrics=report.metrics, escalation=escalation
        )
        if not outcome.changed:
            stop_reason = "The recipe produced no further change."
            break

        attempted.update(outcome.addressed)
        passes = pass_number

        if not write_srgb_jpeg(outcome.image, destination, quality):
            return AdaptiveResult(
                success=False,
                target=goal,
                passes=passes,
                initial_score=initial_score,
                stop_reason="Failed to write the corrected image.",
                log=log.to_list(),
            )

        report = score_image(destination, config=cfg, semantic=semantic)
        progress = _progress(report, goal)
        gain = report.score - previous_score

        changed = ", ".join(
            f"{step.operation} ({step.strength:.2f})" for step in outcome.steps
        )
        log.change(
            f"Pass {pass_number}: applied {changed}.",
            pass_number=pass_number,
            score=report.score,
        )
        log.info(
            f"Pass {pass_number}: score {previous_score * 100:.1f}% → "
            f"{report.score * 100:.1f}% (Δ{gain * 100:+.1f}pt). "
            f"{_describe_progress(progress)}",
            pass_number=pass_number,
            score=report.score,
        )

        if report.score > best[1].score:
            best = (outcome.image, report, progress)
        elif report.score < best[1].score:
            # Escalation backfired. Keep the better file and stop climbing.
            log.warn(
                f"Pass {pass_number}: score dropped below the best result "
                f"({best[1].score * 100:.1f}%); reverting to the best image and "
                "stopping escalation.",
                pass_number=pass_number,
                score=report.score,
            )
            working, report, progress = best
            if not write_srgb_jpeg(working, destination, quality):
                return AdaptiveResult(
                    success=False,
                    target=goal,
                    passes=passes,
                    initial_score=initial_score,
                    stop_reason="Failed to restore the best image.",
                    log=log.to_list(),
                )
            stop_reason = (
                f"Corrections stopped helping at {report.score * 100:.1f}% "
                "(a stronger pass scored worse and was reverted)."
            )
            break

        # No measurable gain means the strength cap is binding for this issue.
        # Escalating further is still worth one more try, but once the clamp is
        # saturated a further pass would just reproduce the same image.
        if gain < MIN_MEANINGFUL_GAIN:
            if escalation >= _max_escalation():
                stop_reason = _stuck_reason(progress)
                # The headline stays short; the reason each dimension is stuck is
                # what actually tells the operator what to do next.
                for dim in progress.unmet_fixable:
                    log.warn(diagnose_stuck(dim), pass_number=pass_number, score=report.score)
                for dim in progress.unmet_manual:
                    log.warn(diagnose_stuck(dim), pass_number=pass_number, score=report.score)
                break
            log.warn(
                f"Pass {pass_number}: gain below {MIN_MEANINGFUL_GAIN * 100:.1f}pt; "
                "increasing correction strength and retrying.",
                pass_number=pass_number,
                score=report.score,
            )
            escalation *= ESCALATION_STEP
        else:
            previous_score = report.score

        if report.passed and progress.all_met:
            stop_reason = "Target reached and the image now passes Adobe's threshold."
            break

    else:
        stop_reason = f"Reached the {max_passes}-pass limit."

    if not stop_reason:
        stop_reason = "Finished."

    if passes == 0 and not container.changed:
        stop_reason = "Nothing was auto-fixable."

    # Deliver the best image the loop produced, not merely the last one. A pass
    # that scored worse is reverted above, and a loop that never beat its input
    # must still leave the corrected copy rather than a degraded file.
    working, report, progress = best

    if not destination.is_file():
        if not write_srgb_jpeg(working, destination, quality):
            return AdaptiveResult(
                success=False,
                target=goal,
                initial_score=initial_score,
                stop_reason="Failed to write the corrected image.",
                log=log.to_list(),
            )
        report = score_image(destination, config=cfg, semantic=semantic)
        progress = _progress(report, goal)

    log.info(f"Stopped: {stop_reason}", score=report.score)

    result = AdaptiveResult(
        success=True,
        output_path=str(destination),
        passes=passes,
        initial_score=initial_score,
        final_score=report.score,
        initial_passed=initial_score >= cfg.threshold,
        final_passed=report.passed,
        target=goal,
        # Recomputed from the source file rather than reusing the in-loop value,
        # so "before" always describes the operator's original input even when
        # the loop reverted to an earlier state.
        progress_before=_progress(
            score_image(source, config=cfg, semantic=semantic), goal
        ),
        progress_after=progress,
        manual=sorted({issue.code for issue in report.issues if not issue.refinable}),
        remaining_fixable=sorted(
            {issue.code for issue in report.issues if issue.refinable}
        ),
        stop_reason=stop_reason,
        srgb_embedded=has_srgb_profile(destination),
        # Derived from the log rather than tracked separately, so the two views
        # of the run can never disagree.
        history=[
            {"pass": entry["pass"], "note": entry["message"], "score": entry["score"]}
            for entry in log.to_list()
            if entry["level"] in ("change", "stop", "warn") and entry["pass"] > 0
        ],
        log=log.to_list(),
        report=report,
    )

    # Judge success by measurement movement, as the single-shot engine does -
    # then subtract anything still outstanding. A dimension can improve while
    # still listing the same issue code (a partial improvement earns no score
    # credit, but the issue has not gone away), and listing one code as both
    # "fixed" and "still fixable" would read as nonsense in the UI.
    resolved = _resolved_codes(attempted, result.progress_before, progress)
    outstanding = set(result.remaining_fixable) | set(result.manual)
    result.fixed = [code for code in resolved if code not in outstanding]

    if result.target_met:
        log.done(f"Target met at {report.score * 100:.1f}%.", score=report.score)
    elif progress.blocked_by_manual:
        blockers = ", ".join(d.label for d in progress.unmet_manual)
        log.warn(
            f"Auto-fixable dimensions are done, but {blockers} still need a manual "
            "decision - the engine cannot lift those.",
            score=report.score,
        )
    log.done(f"Run complete: {result.fixed or 'no issues resolved'}.", score=report.score)
    result.log = log.to_list()
    return result


def _max_escalation() -> float:
    """Largest multiplier the clamp will honour before it stops mattering."""
    from services.refine.recipe import ABSOLUTE_MAX_STRENGTH, MAX_CORRECTION_STRENGTH

    return ABSOLUTE_MAX_STRENGTH / MAX_CORRECTION_STRENGTH


def _stuck_reason(progress: TargetProgress) -> str:
    """Concise one-line explanation of a plateau.

    The detailed per-dimension diagnosis goes to the log instead, so this stays
    readable in the UI banner where it is the headline.
    """
    stuck = progress.unmet_fixable
    if stuck:
        labels = ", ".join(d.label for d in stuck)
        return (
            f"Plateau at {progress.overall_score * 100:.1f}%: {labels} did not move "
            "even at maximum correction strength."
        )
    if progress.unmet_manual:
        labels = ", ".join(d.label for d in progress.unmet_manual)
        return (
            f"Plateau at {progress.overall_score * 100:.1f}%; {labels} can only be "
            "resolved manually."
        )
    return f"Plateau at {progress.overall_score * 100:.1f}%."


def _resolved_codes(
    attempted: set[str], before: TargetProgress | None, after: TargetProgress
) -> list[str]:
    """Codes whose dimension score actually improved."""
    if before is None:
        return []
    before_by_code: dict[str, float] = {}
    for dim in before.dimensions:
        for code in dim.fixable_codes:
            before_by_code[code] = dim.score

    after_by_code: dict[str, float] = {}
    for dim in after.dimensions:
        for code in dim.fixable_codes:
            after_by_code[code] = dim.score

    resolved = []
    for code in attempted:
        was = before_by_code.get(code)
        now = after_by_code.get(code)
        if was is None and now is None:
            # The issue disappeared entirely: its dimension no longer lists it.
            resolved.append(code)
        elif was is None or now is None:
            resolved.append(code)
        elif now > was:
            resolved.append(code)
    return sorted(resolved)
