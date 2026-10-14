"use client";

import { useState } from "react";

/** True when a JSON-column value carries nothing worth rendering. */
export function isEmptyValue(value: unknown): boolean {
  if (value == null || value === "") return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  return false;
}

/** Compact one-line preview: strings as-is, objects as short JSON. */
function previewOf(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    const json = JSON.stringify(value) ?? String(value);
    return json.length > 120 ? `${json.slice(0, 117)}…` : json;
  } catch {
    return String(value);
  }
}

/** Full pretty-printed text for the expanded view. */
function fullOf(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    return String(value);
  }
}

interface JsonValueProps {
  label: string;
  value: unknown;
}

/**
 * A stage-details / acceptance-report value that fits the dense row by
 * default but expands in place on click.
 *
 * The panel used to truncate every JSON blob to one line (with only a hover
 * tooltip for the rest), so fields like the refine report or metrics were
 * effectively unreadable. Clicking the row now swaps the preview for the full
 * pretty-printed JSON in a scrollable block; a second click folds it back —
 * the panel is narrow by design, so the value grows *downward* instead of
 * widening the panel over the image.
 */
export default function JsonValue({ label, value }: JsonValueProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="py-0.5">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        title={expanded ? "Collapse" : "Show the full value"}
        className="flex w-full items-baseline justify-between gap-3 rounded-sm text-left hover:bg-parchment-50/10"
      >
        <span className="label-caps shrink-0">{label}</span>
        <span
          className={`min-w-0 text-right font-stamp text-[11px] text-ink-200 ${
            expanded ? "truncate" : "truncate"
          }`}
        >
          {expanded ? "▾ full value" : previewOf(value)}
        </span>
      </button>
      {expanded && (
        <pre className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-sm border border-parchment-400/40 bg-ink-900/60 p-2 font-stamp text-[10px] leading-relaxed text-ink-200">
          {fullOf(value)}
        </pre>
      )}
    </div>
  );
}
