"use client";

/**
 * The agent's tool activity, one row per call — which site was opened, what
 * query ran, and whether the step succeeded.
 *
 * A **failed step is rendered distinctly** (oxblood, not olive) rather than
 * hidden, because a blocked search is the single most important thing to see:
 * an operator who cannot tell "no competition" from "could not look" will make
 * the wrong decision about a niche.
 */
import { AlertTriangle, CheckCircle2, ChevronRight, Loader2 } from "lucide-react";
import { useState } from "react";

import type { ToolStep } from "@/lib/researchStream";

interface ToolStepsProps {
  steps: ToolStep[];
}

export default function ToolSteps({ steps }: ToolStepsProps) {
  if (steps.length === 0) return null;

  return (
    <ol className="space-y-1.5">
      {steps.map((step) => (
        <ToolStepRow key={step.id} step={step} />
      ))}
    </ol>
  );
}

function ToolStepRow({ step }: { step: ToolStep }) {
  const [isOpen, setOpen] = useState(false);
  const isPending = !step.result;
  const isFailed = step.result != null && !step.result.ok;

  return (
    <li
      className={`rounded-sm border px-2.5 py-1.5 text-xs ${
        isFailed
          ? "border-oxblood-500/40 bg-oxblood-400/10"
          : "border-parchment-400 bg-parchment-100"
      }`}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0">
          {isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-brass-400" aria-hidden />
          ) : isFailed ? (
            <AlertTriangle className="h-3.5 w-3.5 text-oxblood-400" aria-hidden />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-olive-400" aria-hidden />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="truncate font-body text-ink-800">{step.summary}</span>
            {step.result?.durationSeconds != null && (
              <span className="shrink-0 tabular-nums text-ink-400">
                {step.result.durationSeconds}s
              </span>
            )}
          </div>

          {step.result && (
            <p
              className={`mt-0.5 leading-relaxed ${
                isFailed ? "text-oxblood-400" : "text-ink-400"
              }`}
            >
              {step.result.summary}
            </p>
          )}

          <button
            type="button"
            onClick={() => setOpen((open) => !open)}
            aria-expanded={isOpen}
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-ink-400 transition-colors hover:text-brass-300"
          >
            <ChevronRight
              className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
              aria-hidden
            />
            {isOpen ? "Hide" : "Show"} arguments
          </button>

          {isOpen && (
            <pre className="mt-1 overflow-x-auto rounded-sm border border-parchment-400 bg-parchment-100 px-2 py-1.5 text-[11px] leading-relaxed text-ink-400">
              {JSON.stringify(step.arguments, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </li>
  );
}
