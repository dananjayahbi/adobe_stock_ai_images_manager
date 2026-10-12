"use client";

import type { RecordFilters } from "@/lib/records";

export interface GalleryFilters extends RecordFilters {
  stage: string;
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
 * Options mirror what `/api/records` actually supports: pipeline stage and
 * usage. Anything richer would be a lie the backend could not honour.
 */
const STAGES: { value: string; label: string }[] = [
  { value: "", label: "Any stage" },
  // The gallery's default lens (mirrors page.tsx's initial state — the value
  // must match exactly or the <select> would render blank). Backend accepts
  // comma-separated stage lists, and this pair is the app's own "publishable"
  // rule (same stages as `only_ready` in the CSV builder).
  { value: "METADATA_READY,PUBLISHED", label: "Ready to publish" },
  { value: "COLLECTED", label: "Collected" },
  { value: "OCR_CLEAR", label: "OCR clear" },
  { value: "OCR_REJECTED", label: "OCR rejected" },
  { value: "UPSCALED", label: "Upscaled" },
  { value: "REFINED", label: "Refined" },
  { value: "COMPATIBLE", label: "Compatible" },
  { value: "INCOMPATIBLE", label: "Incompatible" },
  { value: "METADATA_READY", label: "Metadata ready" },
  { value: "PUBLISHED", label: "Published" },
  { value: "QUARANTINED", label: "Quarantined" },
];

const USAGE: { value: GalleryFilters["used"]; label: string }[] = [
  { value: "all", label: "Any usage" },
  { value: "unused", label: "Unused" },
  { value: "used", label: "Used" },
];

const SELECT_CLASS =
  "rounded-sm border border-parchment-500 bg-parchment-50 px-2.5 py-1.5 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400";

export default function FilterBar({ filters, onChange }: FilterBarProps) {
  const active = filters.stage !== "" || filters.used !== "all";

  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Image filters">
      <label className="sr-only" htmlFor="filter-stage">
        Stage
      </label>
      <select
        id="filter-stage"
        className={SELECT_CLASS}
        value={filters.stage}
        onChange={(event) => onChange({ ...filters, stage: event.target.value })}
      >
        {STAGES.map((stage) => (
          <option key={stage.value} value={stage.value}>
            {stage.label}
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
          onClick={() => onChange({ ...filters, stage: "", used: "all" })}
          className="rounded-sm border border-transparent px-2 py-1.5 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 hover:text-ink-800"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
