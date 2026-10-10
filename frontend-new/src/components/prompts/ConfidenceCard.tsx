"use client";

/**
 * The validity scorecard, plus the follow-up actions the validity event
 * carries.
 *
 * Two deliberate behaviours:
 *
 * * **The disclaimer renders unconditionally and in full**, not as a tooltip.
 *   The scores look like measurements and nothing here can measure customer
 *   demand — an operator who reads "72% download confidence" without the
 *   caveat may make a portfolio decision on a judgement.
 * * **The follow-up buttons come from the backend's `follow_up_actions`**
 *   (`{id, label, message}`) and send each action's own `message`. Nothing is
 *   hard-coded in the UI, so the buttons and the agent's instructions cannot
 *   disagree about what the operator is being asked.
 *
 * Keyed on an explicit `meets_target === false` rather than falsiness: an
 * absent verdict must say "unknown", never render "Below the undefined% target".
 */
import { ArrowRight, Info, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";

import Button from "@/components/ui/Button";
import type { FollowUpAction, ResearchValidity } from "@/lib/research";

interface ConfidenceCardProps {
  validity: ResearchValidity;
  followUpActions: FollowUpAction[];
  /** Sends the action's own `message` as a follow-up turn. */
  onFollowUp: (action: FollowUpAction) => void;
  /** Follow-up buttons hide while a turn streams. */
  disabled?: boolean;
}

const BAND_TONE: Record<string, string> = {
  strong: "text-olive-400",
  moderate: "text-brass-300",
  weak: "text-oxblood-400",
  unknown: "text-ink-400",
};

const BAND_BAR: Record<string, string> = {
  strong: "bg-olive-500",
  moderate: "bg-brass-400",
  weak: "bg-oxblood-500",
  unknown: "bg-parchment-500",
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
        <span className={`text-xs ${emphasis ? "text-ink-800" : "text-ink-600"}`}>
          {label}
        </span>
        <span
          className={`tabular-nums ${emphasis ? "text-lg" : "text-sm"} font-display ${
            BAND_TONE[band] ?? "text-ink-600"
          }`}
        >
          {value}%
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-parchment-200">
        <div
          className={`h-full rounded-full ${BAND_BAR[band] ?? "bg-parchment-500"}`}
          style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
        />
      </div>
    </div>
  );
}

export default function ConfidenceCard({
  validity,
  followUpActions,
  onFollowUp,
  disabled = false,
}: ConfidenceCardProps) {
  const isStrong = validity.collective_band === "strong";
  const isWeak = validity.collective_band === "weak";

  return (
    <section aria-label="Validity assessment" className="frame-card px-5 py-4">
      <header className="flex items-center gap-2">
        {isStrong ? (
          <TrendingUp className="h-4 w-4 text-olive-400" aria-hidden />
        ) : (
          <TrendingDown
            className={`h-4 w-4 ${isWeak ? "text-oxblood-400" : "text-brass-400"}`}
            aria-hidden
          />
        )}
        <p className="label-caps">Validity assessment</p>
        <span className="ml-auto text-xs text-ink-400">
          {validity.collective_label}
        </span>
      </header>

      {/* What was assessed — the numbers are meaningless without it. */}
      {validity.subject && (
        <p className="mt-3 text-sm leading-relaxed text-ink-600">
          <span className="text-ink-400">Assessed idea: </span>
          <span className="text-ink-800">{validity.subject}</span>
        </p>
      )}

      <div className="mt-3 space-y-3">
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

      {/* The verdict against the target — "unknown" when the backend derived none. */}
      <p
        className={`mt-3 rounded-sm border px-3 py-2 text-xs leading-relaxed ${
          validity.meets_target === true
            ? "border-olive-500/60 bg-olive-400/10 text-olive-400"
            : validity.meets_target === false
              ? "border-brass-400/60 bg-brass-300/10 text-brass-300"
              : "border-parchment-500 bg-parchment-100 text-ink-400"
        }`}
      >
        {validity.meets_target === true
          ? `Reaches the ${validity.target_average}% target.`
          : validity.meets_target === false
            ? `Below the ${validity.target_average}% target — keep researching for a stronger idea.`
            : "This assessment did not report whether it reached the target."}
      </p>

      {validity.reasoning && (
        <div className="mt-3">
          <p className="label-caps">Why</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-600">
            {validity.reasoning}
          </p>
        </div>
      )}

      {validity.evidence.length > 0 && (
        <div className="mt-3">
          <p className="label-caps">Evidence</p>
          <ul className="mt-1 space-y-1">
            {validity.evidence.map((item, index) => (
              <li
                key={`${index}-${item.slice(0, 16)}`}
                className="flex gap-2 text-xs leading-relaxed text-ink-600"
              >
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brass-400" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {validity.recommendation && (
        <p className="mt-3 text-sm leading-relaxed text-ink-800">
          {validity.recommendation}
        </p>
      )}

      {/* The gate: the backend's own choices, each sending its own message. */}
      {followUpActions.length > 0 && !disabled && (
        <div className="mt-4 flex flex-wrap gap-2 border-t border-dashed border-parchment-400 pt-3">
          {followUpActions.map((action) => (
            <Button
              key={action.id}
              size="sm"
              variant={action.id === "continue" ? "primary" : "secondary"}
              type="button"
              onClick={() => onFollowUp(action)}
            >
              {action.id === "continue" ? (
                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" aria-hidden />
              )}
              {action.label}
            </Button>
          ))}
        </div>
      )}

      <p className="mt-4 flex gap-2 rounded-sm border border-parchment-400 bg-parchment-100 px-3 py-2 text-xs leading-relaxed text-ink-400">
        <Info className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
        <span>{validity.disclaimer}</span>
      </p>
    </section>
  );
}
