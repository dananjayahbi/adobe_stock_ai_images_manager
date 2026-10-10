"use client";

/**
 * The library's two controls: a debounced search box and the status filter
 * tabs.
 *
 * Every tab shows its own count so an empty filter is obvious before it is
 * clicked — otherwise selecting "Archived" on a library with nothing filed
 * away looks like a broken list rather than an empty one.
 */
import type { PromptFilter } from "@/lib/prompts";
import type { PromptLibraryTotals } from "@/hooks/usePromptLibrary";

interface LibraryFiltersProps {
  query: string;
  onQueryChange: (next: string) => void;
  filter: PromptFilter;
  onFilterChange: (next: PromptFilter) => void;
  totals: PromptLibraryTotals;
}

interface TabSpec {
  id: PromptFilter;
  label: string;
  hint: string;
}

const TABS: TabSpec[] = [
  { id: "all", label: "All", hint: "Every prompt in the library" },
  {
    id: "used",
    label: "Used",
    hint: "Consumed — marked used by hand",
  },
  {
    id: "unused",
    label: "Unused",
    hint: "Still a draft — not consumed yet",
  },
  { id: "archived", label: "Archived", hint: "Filed away" },
];

function countOf(filter: PromptFilter, totals: PromptLibraryTotals): number {
  switch (filter) {
    case "all":
      return totals.total;
    case "used":
      return totals.used;
    case "unused":
    case "draft":
      return totals.unused;
    case "archived":
      return totals.archived;
  }
}

export default function LibraryFilters({
  query,
  onQueryChange,
  filter,
  onFilterChange,
  totals,
}: LibraryFiltersProps) {
  return (
    <div className="space-y-3">
      <div>
        <label htmlFor="prompt-search" className="sr-only">
          Search prompts
        </label>
        <input
          id="prompt-search"
          type="search"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Search titles, bodies, tags…"
          className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 placeholder:text-ink-400 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
        />
      </div>

      <div
        role="tablist"
        aria-label="Prompt filters"
        className="flex flex-wrap items-center gap-1.5"
      >
        {TABS.map((tab) => {
          const count = countOf(tab.id, totals);

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={filter === tab.id}
              onClick={() => onFilterChange(tab.id)}
              title={tab.hint}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm border px-2.5 py-1 font-stamp text-[11px] uppercase tracking-[0.14em] transition-colors ${
                filter === tab.id
                  ? "border-oxblood-500 bg-oxblood-500/10 text-oxblood-400"
                  : "border-parchment-500 text-ink-600 hover:border-brass-400 hover:text-ink-800"
              }`}
            >
              {tab.label}
              <span className="tabular-nums opacity-70">{count}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
