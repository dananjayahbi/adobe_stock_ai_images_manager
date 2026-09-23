"use client";

import { Info, TrendingDown, TrendingUp } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ResearchValidity } from "@/lib/research";

export interface ConfidenceCardProps {
  validity: ResearchValidity;
  className?: string;
}

const BAND_TONE: Record<string, string> = {
  strong: "text-emerald-300",
  moderate: "text-amber-300",
  weak: "text-red-300",
  unknown: "text-navy-400",
};

const BAND_BAR: Record<string, string> = {
  strong: "bg-emerald-400",
  moderate: "bg-amber-400",
  weak: "bg-red-400",
  unknown: "bg-navy-600",
};

/** One score with its bar. */
function ScoreBar({
  label,
  value,
  band,
  emphasis = false,
}: {
  label: string;
  value: number;
  band: string;
  emphasis?: boolean;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={cn(
            "text-xs",
            emphasis ? "font-semibold text-navy-100" : "text-navy-300"
          )}
        >
          {label}
        </span>
        <span
          className={cn(
            "tabular-nums",
            emphasis ? "text-base font-semibold" : "text-sm font-medium",
            BAND_TONE[band] ?? "text-navy-300"
          )}
        >
          {value}%
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-navy-750">
        <div
          className={cn("h-full rounded-full", BAND_BAR[band] ?? "bg-navy-600")}
          style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

/**
 * The validity scorecard.
 *
 * The disclaimer is rendered **unconditionally and in full**, not as a tooltip.
 * The scores look like measurements, and nothing in this feature can measure
 * customer demand — so an operator who reads "72% customer download confidence"
 * without the caveat may make a portfolio decision on a number that is a
 * judgement. That is the most damaging thing this feature could do, which is why
 * the caveat is part of the card rather than a detail the UI may drop.
 */
export default function ConfidenceCard({ validity, className }: ConfidenceCardProps) {
  const isStrong = validity.collective_band === "strong";
  const isWeak = validity.collective_band === "weak";

  return (
    <section
      className={cn(
        "space-y-3 rounded-xl border border-navy-700/50 bg-navy-850/50 p-3.5",
        className
      )}
    >
      <header className="flex items-center gap-2">
        {isStrong ? (
          <TrendingUp className="h-4 w-4 text-emerald-300" aria-hidden />
        ) : (
          <TrendingDown
            className={cn("h-4 w-4", isWeak ? "text-red-300" : "text-amber-300")}
            aria-hidden
          />
        )}
        <h3 className="text-sm font-semibold text-navy-100">Validity assessment</h3>
        <span className="ml-auto text-xs text-navy-400">
          {validity.collective_label}
        </span>
      </header>

      <div className="space-y-3">
        <ScoreBar
          label="Customer download confidence"
          value={validity.customer_download_confidence}
          band={validity.download_band}
        />
        <ScoreBar
          label="Adobe Stock acceptance confidence"
          value={validity.adobe_acceptance_confidence}
          band={validity.acceptance_band}
        />
        <ScoreBar
          label="Collective average"
          value={validity.collective_average}
          band={validity.collective_band}
          emphasis
        />
      </div>

      {validity.reasoning ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
            Why
          </h4>
          <p className="mt-1 text-xs leading-relaxed text-navy-300">
            {validity.reasoning}
          </p>
        </div>
      ) : null}

      {validity.evidence.length > 0 ? (
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
            Evidence
          </h4>
          <ul className="mt-1 space-y-1">
            {validity.evidence.map((item, index) => (
              <li
                key={`${index}-${item.slice(0, 16)}`}
                className="flex gap-2 text-xs leading-relaxed text-navy-300"
              >
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-navy-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="text-xs leading-relaxed text-navy-200">{validity.recommendation}</p>

      <p className="flex gap-2 rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2 text-[11px] leading-relaxed text-navy-400">
        <Info className="mt-0.5 h-3 w-3 shrink-0 text-navy-500" aria-hidden />
        <span>{validity.disclaimer}</span>
      </p>
    </section>
  );
}
