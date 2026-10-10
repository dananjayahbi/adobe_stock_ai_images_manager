/**
 * Date helpers for the prompts feature.
 *
 * The API serialises timestamps as naive UTC strings (no `Z`/offset), and
 * `new Date(...)` parses those as *local* time — shifting every date by the UTC
 * offset. These helpers suffix a zone-less timestamp with `Z` before parsing, so
 * the displayed date is the one the server meant.
 */

/** Parse a possibly naive ISO timestamp, treating zone-less values as UTC. */
export function parseServerDate(iso: string | null | undefined): Date | null {
  const raw = (iso ?? "").trim();
  if (!raw) return null;
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(raw);
  const date = new Date(hasZone ? raw : `${raw}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Locale date for a server timestamp, e.g. "10/3/2026". */
export function formatNaiveUtcDate(iso: string | null | undefined): string {
  const date = parseServerDate(iso);
  return date ? date.toLocaleDateString() : "";
}
