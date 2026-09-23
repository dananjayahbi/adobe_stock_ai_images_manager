"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Wrench,
} from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";
import type { ToolStep } from "@/lib/researchStream";

export interface ToolStepListProps {
  steps: ToolStep[];
  className?: string;
}

/**
 * The agent's tool activity, one row per call.
 *
 * This is the "real-time process inspection" the operator asked for: which site
 * was opened, what query was searched, and whether the step succeeded. A **failed
 * step is rendered distinctly** (amber, not green) rather than being hidden,
 * because a blocked search is the single most important thing to see — an
 * operator who cannot tell "no competition" from "could not look" will make the
 * wrong decision about a niche.
 */
export default function ToolStepList({ steps, className }: ToolStepListProps) {
  if (steps.length === 0) return null;

  return (
    <ol className={cn("space-y-1.5", className)}>
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
      className={cn(
        "rounded-lg border px-2.5 py-1.5 text-xs",
        isFailed
          ? "border-amber-500/40 bg-amber-500/10"
          : "border-navy-700/40 bg-navy-850/40"
      )}
    >
      <div className="flex items-start gap-2">
        <span className="mt-0.5 shrink-0">
          {isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-300" aria-hidden />
          ) : isFailed ? (
            <AlertTriangle className="h-3.5 w-3.5 text-amber-300" aria-hidden />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-hidden />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <Wrench className="h-3 w-3 shrink-0 text-navy-500" aria-hidden />
            <span className="truncate font-medium text-navy-200">{step.summary}</span>
            {step.result?.durationSeconds != null ? (
              <span className="shrink-0 tabular-nums text-navy-500">
                {step.result.durationSeconds}s
              </span>
            ) : null}
          </div>

          {step.result ? (
            <p
              className={cn(
                "mt-0.5 leading-relaxed",
                isFailed ? "text-amber-200/90" : "text-navy-400"
              )}
            >
              {step.result.summary}
            </p>
          ) : null}

          <button
            type="button"
            onClick={() => setOpen((open) => !open)}
            aria-expanded={isOpen}
            className="mt-1 inline-flex items-center gap-1 text-[11px] text-navy-500 transition-colors hover:text-navy-300"
          >
            <ChevronRight
              className={cn("h-3 w-3 transition-transform", isOpen && "rotate-90")}
              aria-hidden
            />
            {isOpen ? "Hide" : "Show"} arguments
          </button>

          {isOpen ? (
            <pre className="mt-1 overflow-x-auto rounded-md border border-navy-700/40 bg-navy-900/60 px-2 py-1.5 text-[11px] leading-relaxed text-navy-400">
              {JSON.stringify(step.arguments, null, 2)}
            </pre>
          ) : null}
        </div>
      </div>
    </li>
  );
}
