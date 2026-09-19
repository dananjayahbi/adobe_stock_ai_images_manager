"use client";

/**
 * Auto-fix panel for the inspection modal.
 *
 * The acceptance report has always labelled issues "auto-fixable" without
 * offering any way to fix them. This panel is the missing half: it corrects
 * exactly the issues on screen, then reports what actually changed so the result
 * can be judged rather than trusted.
 *
 * Two modes are offered because they do genuinely different jobs:
 *
 * - **Quick fix** - one pass of the recipe. Fast.
 * - **Deep fix** - repeats with escalating strength until every fixable
 *   dimension reaches a target the operator chooses. This is the mode that can
 *   move the acceptance score, because the single-pass recipe recomputes
 *   identical strengths each run and is therefore idempotent.
 *
 * The copy is deliberately honest about the outcomes that are *not* failures: a
 * fix that improves the score without clearing the threshold, and issues that
 * need a human decision (a model release, a suspected logo). When the loop
 * plateaus, the reason is stated rather than left to inference.
 */

import { AlertCircle, CheckCircle2, Info, Wrench } from "lucide-react";
import { useState } from "react";

import AutoFixControls from "@/components/stages/AutoFixControls";
import AutoFixDimensions from "@/components/stages/AutoFixDimensions";
import AutoFixLog from "@/components/stages/AutoFixLog";
import {
  AUTOFIX_DEFAULT_TARGET,
  autoFixRecord,
  type AutoFixMode,
  type AutoFixResult,
  type ImageRecord,
} from "@/lib/api";
import { issueLabel } from "@/lib/acceptanceIssues";

interface AutoFixPanelProps {
  record: ImageRecord;
  /** Issue codes the last report marked as auto-fixable. */
  fixableCodes: string[];
  /** Called after a successful fix so the caller refetches the preview. */
  onFixed: (result: AutoFixResult) => void;
}

export default function AutoFixPanel({
  record,
  fixableCodes,
  onFixed,
}: AutoFixPanelProps) {
  const [mode, setMode] = useState<AutoFixMode>("single");
  const [target, setTarget] = useState(AUTOFIX_DEFAULT_TARGET);
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AutoFixResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasFixable = fixableCodes.length > 0;

  async function handleRun() {
    setIsRunning(true);
    setError(null);
    try {
      const outcome = await autoFixRecord(record.id, { mode, target });
      setResult(outcome);
      onFixed(outcome);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The auto-fix failed.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
      <div className="min-w-0">
        <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-violet-200">
          <Wrench className="h-3.5 w-3.5" aria-hidden />
          Auto-fix
        </h4>
        <p className="mt-1 text-xs text-navy-300">
          {hasFixable
            ? `${fixableCodes.length} fixable issue type(s) detected: ${fixableCodes
                .map(issueLabel)
                .join(", ")}.`
            : "No automatically fixable issues were detected in the last check."}
        </p>
      </div>

      <AutoFixControls
        mode={mode}
        onModeChange={setMode}
        target={target}
        onTargetChange={setTarget}
        disabled={!hasFixable}
        isRunning={isRunning}
        onRun={() => void handleRun()}
      />

      {error ? (
        <p className="flex items-start gap-1.5 rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-200">
          <AlertCircle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          {error}
        </p>
      ) : null}

      {result ? <AutoFixOutcome result={result} /> : null}
    </div>
  );
}

/** What the fix actually did, and what still stands in the way. */
function AutoFixOutcome({ result }: { result: AutoFixResult }) {
  const tone = result.final_passed
    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
    : result.improved
      ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
      : "border-navy-600/50 bg-navy-700/20 text-navy-200";

  const Icon = result.final_passed
    ? CheckCircle2
    : result.improved
      ? Info
      : AlertCircle;

  const isAdaptive = result.mode === "adaptive";

  return (
    <div className="space-y-2.5">
      <div className={`flex items-start gap-2 rounded border px-2.5 py-2 text-xs ${tone}`}>
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">
            Score {(result.initial_score * 100).toFixed(1)}% →{" "}
            {(result.final_score * 100).toFixed(1)}%
            {result.final_passed
              ? " — now passes."
              : result.improved
                ? " — improved, still below threshold."
                : " — unchanged."}
          </p>
          <p className="opacity-90">
            {result.passes > 0
              ? `${result.passes} correction pass(es).`
              : "No pixel correction was needed."}{" "}
            {result.srgb_embedded
              ? "Output carries an embedded sRGB profile."
              : "Output is not sRGB-tagged."}
          </p>
        </div>
      </div>

      {/*
       * The plateau reason. This is the single most valuable line when the score
       * did not move, because the usual cause is a cap the engine cannot touch
       * rather than a failed correction.
       */}
      {result.stop_reason && !result.final_passed ? (
        <p className="rounded border border-navy-700/60 bg-navy-900/60 px-2.5 py-1.5 text-[11px] text-navy-300">
          <span className="font-semibold text-navy-200">Why it stopped: </span>
          {result.stop_reason}
        </p>
      ) : null}

      {isAdaptive && result.progress_after ? (
        <AutoFixDimensions
          progress={result.progress_after}
          before={result.progress_before}
        />
      ) : null}

      {result.fixed.length > 0 ? (
        <ChipList label="Fixed" codes={result.fixed} tone="emerald" />
      ) : null}

      {result.remaining_fixable.length > 0 && !result.target_met ? (
        <ChipList
          label="Still fixable — run Deep fix"
          codes={result.remaining_fixable}
          tone="violet"
        />
      ) : null}

      {result.manual.length > 0 ? (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
            Needs a manual decision
          </p>
          <ul className="space-y-1">
            {result.manual.map((code) => (
              <li key={code} className="flex items-start gap-1.5 text-[11px] text-navy-300">
                <AlertCircle
                  className="mt-0.5 h-3 w-3 shrink-0 text-amber-300"
                  aria-hidden
                />
                <span>
                  <span className="font-medium text-navy-200">{issueLabel(code)}</span> —
                  this cannot be corrected automatically and was left untouched.
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <AutoFixLog entries={result.log} />
    </div>
  );
}

function ChipList({
  label,
  codes,
  tone,
}: {
  label: string;
  codes: string[];
  tone: "emerald" | "violet";
}) {
  const styles =
    tone === "emerald"
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
      : "border-violet-500/30 bg-violet-500/10 text-violet-200";

  return (
    <div className="space-y-1">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
        {label}
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {codes.map((code) => (
          <li key={code} className={`rounded border px-1.5 py-0.5 text-[10px] ${styles}`}>
            {issueLabel(code)}
          </li>
        ))}
      </ul>
    </div>
  );
}
