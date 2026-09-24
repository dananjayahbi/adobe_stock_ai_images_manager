/**
 * Presentation helpers for the live context-window indicator.
 *
 * Kept out of the component so the *numbers* can be unit-tested and so the bar,
 * the label and any future surface read the same thresholds. The backend serves
 * `compact_at_share` / `warn_at_share`, and the fallbacks here exist only for the
 * moment before settings load — a bar that renders "0% of unknown" is worse than
 * one that renders nothing.
 */

import type { ResearchContextReport } from "./research";

/** Fallbacks, used only until the settings request returns. */
export const DEFAULT_WARN_AT_SHARE = 0.85;
export const DEFAULT_COMPACT_AT_SHARE = 0.7;

export interface ContextWindowView {
  /** 0-100, for the bar's width. */
  percent: number;
  /** A short label, e.g. `12.4k / 200k`. */
  label: string;
  /** `ok` | `warn` | `critical`, for the colour. */
  level: "ok" | "warn" | "critical";
  /** One sentence explaining the state, for the `title` attribute. */
  detail: string;
  /** True when the operator needs to act (start a new thread). */
  needsAttention: boolean;
}

/** Compact token counts: 12_400 → `12.4k`, 200_000 → `200k`. */
export function formatTokens(tokens: number): string {
  const value = Math.max(0, Math.round(tokens || 0));
  if (value < 1000) return String(value);
  if (value < 100_000) return `${(value / 1000).toFixed(1)}k`;
  return `${Math.round(value / 1000)}k`;
}

/**
 * Derive everything the bar renders from one report.
 *
 * Returns `null` when there is nothing to show — no report yet, or a window of
 * zero — because an indicator that renders an unknown percentage reads as a
 * broken control rather than as an absent one.
 */
export function contextWindowView(
  report: ResearchContextReport | null | undefined
): ContextWindowView | null {
  if (!report || !report.window_tokens || report.window_tokens <= 0) return null;

  const share = report.used_tokens / report.window_tokens;
  const percent = Math.max(0, Math.min(100, Math.round(share * 1000) / 10));
  const level: ContextWindowView["level"] =
    report.level === "critical" || report.level === "warn" ? report.level : "ok";

  const parts = [
    `${formatTokens(report.used_tokens)} of ${formatTokens(report.window_tokens)} tokens used (${percent}%).`,
    `${formatTokens(report.remaining_tokens)} left for the reply.`,
  ];
  if (report.compacted && report.folded_turns > 0) {
    parts.push(
      `${report.folded_turns} older turn${report.folded_turns === 1 ? "" : "s"} were compacted into a summary to make room.`
    );
  }
  if (report.degraded) {
    parts.push("The compaction was degraded, so some earlier detail may be missing.");
  }

  return {
    percent,
    label: `${formatTokens(report.used_tokens)} / ${formatTokens(report.window_tokens)}`,
    level,
    detail: parts.join(" "),
    needsAttention: level === "critical" || report.degraded === true,
  };
}
