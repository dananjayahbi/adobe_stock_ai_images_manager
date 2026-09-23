/**
 * Filter vocabulary for the Prompt Library sidebar.
 *
 * The library has **two independent axes**, and conflating them is the bug this
 * module exists to prevent:
 *
 * - **Status axis** — *has the prompt been consumed?* `draft`, `used`,
 *   `unused`, `archived` read `Prompt.status`. A prompt the operator used
 *   elsewhere is `used` even with nothing collected here.
 * - **Binding axis** — *is it linked to images collected here?* `bound`,
 *   `unbound` read the live binding count.
 *
 * A prompt can therefore be `used` **and** `unbound` at the same time, which is
 * exactly the state the operator previously had no way to see.
 *
 * Keeping the labels, groups and count selectors here means the tab strip and
 * the summary line cannot drift apart, and adding a filter is a one-line change.
 */

import type { PromptFilter, PromptListResponse } from "./prompts";

/** Which question a filter answers. Drives the grouping in the tab strip. */
export type PromptFilterAxis = "status" | "binding" | "all";

export interface PromptFilterSpec {
  id: PromptFilter;
  label: string;
  axis: PromptFilterAxis;
  /** Hover text — states plainly which field the filter reads. */
  hint: string;
}

/**
 * Every filter, in render order: the catch-all, then the status axis, then the
 * binding axis. The order matters because the two groups are labelled.
 */
export const PROMPT_FILTERS: PromptFilterSpec[] = [
  {
    id: "all",
    label: "All",
    axis: "all",
    hint: "Every prompt in the library",
  },
  {
    id: "used",
    label: "Used",
    axis: "status",
    hint: "Consumed — marked used by hand or by binding an image",
  },
  {
    id: "unused",
    label: "Unused",
    axis: "status",
    hint: "Still a draft — not consumed yet",
  },
  {
    id: "bound",
    label: "Bound",
    axis: "binding",
    hint: "Has at least one image bound to it",
  },
  {
    id: "unbound",
    label: "Unbound",
    axis: "binding",
    hint: "No image bound — may still be used",
  },
  {
    id: "archived",
    label: "Archived",
    axis: "status",
    hint: "Filed away",
  },
];

/** Totals keyed by filter id, so a tab can show its own count. */
export type PromptFilterCounts = Record<PromptFilter, number>;

/**
 * Map the list response's totals onto the tabs.
 *
 * The server reports the two axes separately; this is the only place that
 * decides which number each tab shows, so a tab can never display another
 * axis's count.
 */
export function promptFilterCounts(
  totals: Pick<
    PromptListResponse,
    "total" | "used" | "unused" | "bound" | "unbound" | "archived"
  >
): PromptFilterCounts {
  return {
    all: totals.total,
    used: totals.used,
    unused: totals.unused,
    bound: totals.bound,
    unbound: totals.unbound,
    archived: totals.archived,
    // `draft` is the server's name for the same state the UI labels "Unused",
    // so it deliberately reports the identical count rather than a separate
    // query. It is in the vocabulary for API completeness, not as a tab.
    draft: totals.unused,
  };
}

/** Empty-state copy for a filter, so the panel never says "no prompts" wrongly. */
export function promptFilterEmptyMessage(filter: PromptFilter): string {
  switch (filter) {
    case "used":
      return "No consumed prompts";
    case "unused":
      return "No unused prompts";
    case "bound":
      return "No bound prompts";
    case "unbound":
      return "No unbound prompts";
    case "archived":
      return "No archived prompts";
    case "draft":
      return "No draft prompts";
    default:
      return "No prompts yet";
  }
}
