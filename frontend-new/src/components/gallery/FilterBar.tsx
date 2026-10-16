"use client";

import { LIFECYCLE_STATES, STATE_LABELS } from "@/lib/states";
import type { RecordFilters } from "@/lib/records";

export interface GalleryFilters extends RecordFilters {
  state: string;
  used: "all" | "used" | "unused";
}

interface FilterBarProps {
  filters: GalleryFilters;
  onChange: (filters: GalleryFilters) => void;
}

/**
 * Image-level filters for the gallery.
 *
 * Deliberately scoped to *images only* (task rule): a filter never hides or
 * reflows a folder card — folders are the operator's own structure and must
 * stay visible whatever the current lens says.
 *
 * Options mirror what `/api/records?state=` actually supports: comma-separated
 * lifecycle states, plus usage. The "Publishable" composite is the app's own
 * default lens (same states as page.tsx's initial filter) so the select
 * renders a real option on load — its value must match exactly or the
 * `<select>` would render blank. Anything richer would be a lie the backend
 * could not honour.
 */
const STATES: { value: string; label: string }[] = [
  { value: "", label: "Any state" },
  { value: "READY_TO_PUBLISH,PUBLISHED,AS_ACCEPTED", label: "Publishable" },
  ...LIFECYCLE_STATES.map((state) => ({
    value: state,
    label: STATE_LABELS[state],
  })),
];

const USAGE: { value: GalleryFilters["used"]; label: string }[] = [
  { value: "all", label: "Any usage" },
  { value: "unused", label: "Unused" },
  { value: "used", label: "Used" },
];

const SELECT_CLASS =
  "rounded-sm border border-parchment-500 bg-parchment-50 px-2.5 py-1.5 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400";

export default function FilterBar({ filters, onChange }: FilterBarProps) {
  const active = filters.state !== "" || filters.used !== "all";

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Image filters">
      <label className="sr-only" htmlFor="filter-state">
        State
      </label>
      <select
        id="filter-state"
        className={SELECT_CLASS}
        value={filters.state}
        onChange={(event) => onChange({ ...filters, state: event.target.value })}
      >
        {STATES.map((state) => (
          <option key={state.value} value={state.value}>
            {state.label}
          </option>
        ))}
      </select>

      <label className="sr-only" htmlFor="filter-used">
        Usage
      </label>
      <select
        id="filter-used"
        className={SELECT_CLASS}
        value={filters.used}
        onChange={(event) =>
          onChange({ ...filters, used: event.target.value as GalleryFilters["used"] })
        }
      >
        {USAGE.map((usage) => (
          <option key={usage.value} value={usage.value}>
            {usage.label}
          </option>
        ))}
      </select>

      {active && (
        <button
          type="button"
          onClick={() => onChange({ ...filters, state: "", used: "all" })}
          className="rounded-sm border border-transparent px-2 py-1.5 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 hover:text-ink-800"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
