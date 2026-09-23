"use client";

import type { PromptFilterCounts } from "@/lib/promptFilters";

export interface PromptLibrarySummaryProps {
  counts: PromptFilterCounts;
}

/**
 * One-line summary of the library, grouped by axis.
 *
 * Reads the pre-mapped filter counts rather than the raw totals so the numbers
 * here and the numbers on the filter pills can never disagree. The two groups
 * are labelled because they overlap: a prompt counted under "used" may also be
 * counted under "unbound", and an unlabelled "3 used · 5 unbound · 8 total"
 * would look like arithmetic that does not add up.
 */
export function PromptLibrarySummary({ counts }: PromptLibrarySummaryProps) {
  return (
    <p className="truncate text-[11px] text-navy-400">
      {counts.all} prompt{counts.all === 1 ? "" : "s"} ·{" "}
      <span className="text-emerald-300">{counts.used} used</span> ·{" "}
      <span className="text-accent-300">{counts.bound} bound</span> ·{" "}
      {counts.unbound} unbound
    </p>
  );
}

export default PromptLibrarySummary;
