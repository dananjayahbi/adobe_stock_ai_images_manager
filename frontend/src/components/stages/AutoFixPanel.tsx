"use client";

/**
 * "Auto-fix" action for the inspection modal.
 *
 * The acceptance report has always labelled issues "auto-fixable" without
 * offering any way to fix them — the operator's only option was a full Stage 4
 * re-run that silently re-derived its own recipe. This panel is the missing
 * half: it corrects exactly the issues on screen, then reports what actually
 * changed so the result can be judged rather than trusted.
 *
 * The copy is deliberately honest about the two outcomes that are *not*
 * failures: a fix that improves the score without clearing the threshold, and
 * issues that need a human decision (a model release, a suspected logo).
 */

import { AlertCircle, CheckCircle2, Info, Wrench } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { autoFixRecord, type AutoFixResult, type ImageRecord } from "@/lib/api";
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
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<AutoFixResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const hasFixable = fixableCodes.length > 0;

  async function handleAutoFix() {
    setIsRunning(true);
    setError(null);
    try {
      const outcome = await autoFixRecord(record.id);
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
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-violet-200">
            <Wrench className="h-3.5 w-3.5" aria-hidden />
            Auto-fix
          </h4>
          <p className="mt-1 text-xs text-navy-300">
            {hasFixable
              ? `Applies the corrections for ${fixableCodes.length} fixable issue type(s), then re-scores the image.`
              : "No automatically fixable issues were detected in the last check."}
          </p>
        </div>

        <Button
          size="sm"
          variant="primary"
          disabled={!hasFixable || isRunning}
          isLoading={isRunning}
          onClick={() => void handleAutoFix()}
          icon={isRunning ? undefined : <Wrench className="h-3.5 w-3.5" aria-hidden />}
        >
          {isRunning ? "Fixing…" : "Auto-fix & re-check"}
        </Button>
      </div>

      {/* Which codes the engine will attempt. */}
      {hasFixable && !result ? (
        <ul className="flex flex-wrap gap-1.5">
          {fixableCodes.map((code) => (
            <li
              key={code}
              className="rounded border border-violet-500/30 bg-violet-500/10 px-1.5 py-0.5 text-[10px] text-violet-200"
            >
              {issueLabel(code)}
            </li>
          ))}
        </ul>
      ) : null}

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

  return (
    <div className="space-y-2">
      <div className={`flex items-start gap-2 rounded border px-2.5 py-2 text-xs ${tone}`}>
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
        <div className="min-w-0 space-y-0.5">
          <p className="font-medium">
            Score {(result.initial_score * 100).toFixed(1)}% →{" "}
            {(result.final_score * 100).toFixed(1)}%
            {result.final_passed ? " — now passes." : " — still below threshold."}
          </p>
          <p className="opacity-90">
            {result.passes > 0
              ? `${result.passes} correction pass(es) applied.`
              : "No pixel correction was needed."}{" "}
            {result.srgb_embedded
              ? "Output carries an embedded sRGB profile."
              : "Output is not sRGB-tagged."}
          </p>
        </div>
      </div>

      {result.fixed.length > 0 ? (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
            Fixed
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {result.fixed.map((code) => (
              <li
                key={code}
                className="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-200"
              >
                {issueLabel(code)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {result.manual.length > 0 ? (
        <div className="space-y-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
            Needs a manual decision
          </p>
          <ul className="space-y-1">
            {result.manual.map((code) => (
              <li
                key={code}
                className="flex items-start gap-1.5 text-[11px] text-navy-300"
              >
                <AlertCircle className="mt-0.5 h-3 w-3 shrink-0 text-amber-300" aria-hidden />
                <span>
                  <span className="font-medium text-navy-200">{issueLabel(code)}</span> —
                  this cannot be corrected automatically and was left untouched.
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
