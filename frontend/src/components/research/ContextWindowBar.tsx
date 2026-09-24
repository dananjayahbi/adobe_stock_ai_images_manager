"use client";

import { AlertTriangle, Gauge } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ResearchContextReport } from "@/lib/research";
import { contextWindowView } from "@/lib/researchContext";

export interface ContextWindowBarProps {
  report: ResearchContextReport | null;
  /** The window the backend resolved, so the bar can render before a run. */
  fallbackWindow?: number;
  /** True while a turn is running, so the bar reads as live. */
  isLive?: boolean;
  className?: string;
}

/**
 * A live indicator of how full the model's context window is.
 *
 * Why it exists: a long research thread grows with every tool call, and the
 * failure when it overflows is silent — the provider truncates the request from
 * the front, which removes the system prompt, and the run stops for no visible
 * reason. A bar that fills up turns that into something the operator can see
 * coming and act on (start a new thread, or raise the window).
 *
 * Three deliberate choices:
 *
 * * **The thresholds come from the backend.** The same `warn_at_share` and
 *   `compact_at_share` decide when the bar turns amber and when the history is
 *   actually compacted, so the indicator cannot promise room the backend is
 *   about to use.
 * * **Compaction is stated in words, not implied by a colour.** "6 older turns
 *   were compacted" is the fact that explains why the model may not remember an
 *   early detail; a colour alone would not.
 * * **It renders nothing without a measurement.** A bar reading "0% of unknown"
 *   looks like a broken control rather than an absent one.
 */
export default function ContextWindowBar({
  report,
  fallbackWindow = 0,
  isLive = false,
  className,
}: ContextWindowBarProps) {
  const view = contextWindowView(report);

  // Before the first measurement, show the window itself at zero. That is honest
  // (nothing has been sent yet) and keeps the control's position stable, so the
  // bar does not appear from nowhere mid-run and shift the layout.
  if (!view && fallbackWindow <= 0) return null;

  const percent = view?.percent ?? 0;
  const level = view?.level ?? "ok";
  const label = view?.label ?? `0 / ${Math.round(fallbackWindow / 1000)}k`;

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center gap-2 text-[11px]">
        <Gauge
          className={cn(
            "h-3 w-3 shrink-0",
            level === "critical"
              ? "text-red-400"
              : level === "warn"
                ? "text-amber-400"
                : "text-navy-500"
          )}
          aria-hidden
        />
        <span className="font-medium text-navy-400">Context window</span>
        <span className="tabular-nums text-navy-500">{label}</span>
        {isLive ? (
          <span className="text-navy-600" title="Updated as the run streams">
            live
          </span>
        ) : null}
        <span className="ml-auto tabular-nums text-navy-500">{percent}%</span>
      </div>

      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-navy-800"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Context window usage"
        title={view?.detail ?? "No measurement yet."}
      >
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-500",
            level === "critical"
              ? "bg-red-500"
              : level === "warn"
                ? "bg-amber-500"
                : "bg-accent-500"
          )}
          style={{ width: `${percent}%` }}
        />
      </div>

      {view?.needsAttention ? (
        <p className="flex items-start gap-1.5 text-[11px] leading-relaxed text-amber-300">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
          <span>
            {report?.degraded
              ? "This conversation was compacted with a local excerpt, so some earlier detail may be missing."
              : "This conversation is close to the model's context window. Start a new thread, or raise the window in Settings."}
          </span>
        </p>
      ) : null}
    </div>
  );
}
