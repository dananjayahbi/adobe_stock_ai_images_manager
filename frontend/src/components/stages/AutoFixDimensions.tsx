"use client";

/**
 * Per-dimension goal tracking for an adaptive auto-fix run.
 *
 * This is the readout that makes a plateau legible. The overall acceptance score
 * is capped by its worst dimension (``ceiling_floor + ceiling_span * worst``), so
 * a single dimension stuck at 0% holds the total at 55% no matter how many pixel
 * corrections succeed. Showing each dimension against the operator's target makes
 * that obvious, where a lone percentage cannot.
 */

import { AlertTriangle, Check, Minus } from "lucide-react";

import type { AutoFixProgress } from "@/lib/api";
import { cn } from "@/lib/cn";

interface AutoFixDimensionsProps {
  progress: AutoFixProgress;
  /** The "before" snapshot, used to show movement per dimension. */
  before?: AutoFixProgress | null;
}

export default function AutoFixDimensions({
  progress,
  before,
}: AutoFixDimensionsProps) {
  const beforeByKey = new Map(
    (before?.dimensions ?? []).map((dim) => [dim.key, dim.score])
  );
  const targetPercent = Math.round(progress.target * 100);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
          Dimensions vs {targetPercent}% target
        </p>
        {progress.blocked_by_manual ? (
          <span className="flex items-center gap-1 text-[10px] text-amber-300">
            <AlertTriangle className="h-3 w-3" aria-hidden />
            blocked by manual issues
          </span>
        ) : null}
      </div>

      <ul className="space-y-1">
        {progress.dimensions.map((dim) => {
          const met = dim.score >= progress.target;
          const was = beforeByKey.get(dim.key);
          const delta = was === undefined ? null : dim.score - was;
          // A dimension with no fixable codes can never be lifted by the engine,
          // so it is marked "manual" rather than implying a retry would help.
          const state = met ? "met" : dim.is_fixable ? "fixable" : "manual";

          return (
            <li key={dim.key} className="flex items-center gap-2 text-[11px]">
              <span
                className={cn(
                  "grid h-3.5 w-3.5 shrink-0 place-items-center rounded-sm",
                  state === "met" && "bg-emerald-500/25 text-emerald-300",
                  state === "fixable" && "bg-violet-500/25 text-violet-300",
                  state === "manual" && "bg-amber-500/25 text-amber-300"
                )}
                title={
                  state === "met"
                    ? "At or above target"
                    : state === "fixable"
                      ? "Below target - the engine can still attempt this"
                      : "Below target - needs a manual decision"
                }
              >
                {state === "met" ? (
                  <Check className="h-2.5 w-2.5" aria-hidden />
                ) : (
                  <Minus className="h-2.5 w-2.5" aria-hidden />
                )}
              </span>

              <span className="min-w-0 flex-1 truncate text-navy-300">
                {dim.label}
              </span>

              {delta !== null && Math.abs(delta) > 0.0005 ? (
                <span
                  className={cn(
                    "shrink-0 font-mono text-[10px] tabular-nums",
                    delta > 0 ? "text-emerald-300" : "text-red-300"
                  )}
                >
                  {delta > 0 ? "+" : ""}
                  {(delta * 100).toFixed(0)}pt
                </span>
              ) : null}

              <span className="w-10 shrink-0 text-right font-mono text-[10px] tabular-nums text-navy-200">
                {(dim.score * 100).toFixed(0)}%
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
