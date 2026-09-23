"use client";

import { cn } from "@/lib/cn";
import {
  PROMPT_FILTERS,
  type PromptFilterCounts,
} from "@/lib/promptFilters";
import type { PromptFilter } from "@/lib/prompts";

export interface PromptFilterTabsProps {
  filter: PromptFilter;
  counts: PromptFilterCounts;
  onFilterChange: (next: PromptFilter) => void;
}

/**
 * The two-axis filter strip for the Prompt Library.
 *
 * Rendered as one row of pills with a labelled separator between the *status*
 * group and the *binding* group. The groups are visually distinct because the
 * distinction is the point: "Used" answers "have I consumed this prompt?" while
 * "Bound" answers "have I collected what it produced?". Collapsing them into one
 * list of unlabelled pills is what made the two states look like the same thing.
 *
 * Counts are rendered per pill so an empty filter is obvious before it is
 * clicked — otherwise selecting "Bound" on a library with no bindings looks
 * like a broken list rather than an empty one.
 */
export function PromptFilterTabs({
  filter,
  counts,
  onFilterChange,
}: PromptFilterTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Prompt filters"
      className="no-scrollbar -mx-0.5 flex items-center gap-1.5 overflow-x-auto px-0.5"
    >
      {PROMPT_FILTERS.map((entry, index) => {
        const previous = PROMPT_FILTERS[index - 1];
        // A hairline divider marks where the status axis ends and the binding
        // axis begins, without needing a second row.
        const startsNewAxis =
          previous !== undefined && previous.axis !== entry.axis;
        const count = counts[entry.id];

        return (
          <span key={entry.id} className="flex shrink-0 items-center gap-1.5">
            {startsNewAxis ? (
              <span
                aria-hidden
                className="h-4 w-px shrink-0 bg-navy-700/70"
                title="Independent axis: binding, not status"
              />
            ) : null}
            <button
              type="button"
              role="tab"
              aria-selected={filter === entry.id}
              onClick={() => onFilterChange(entry.id)}
              title={entry.hint}
              className={cn(
                "inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1",
                "text-[11px] font-medium transition-colors",
                filter === entry.id
                  ? "border-accent-500 bg-accent-500/15 text-accent-200"
                  : "border-navy-700/60 text-navy-300 hover:border-navy-600 hover:text-navy-100"
              )}
            >
              {entry.label}
              <span
                className={cn(
                  "tabular-nums",
                  filter === entry.id ? "text-accent-300/80" : "text-navy-500"
                )}
              >
                {count}
              </span>
            </button>
          </span>
        );
      })}
    </div>
  );
}

export default PromptFilterTabs;
