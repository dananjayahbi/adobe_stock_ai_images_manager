/**
 * Shared field/label classes for the prompts feature, so every input on the
 * page types and focuses identically without each component re-deriving the
 * vintage treatment.
 */

/** Text input, select and textarea base. */
export const inputClass =
  "w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 placeholder:text-ink-400 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60";

/** Label above a field (the stamp small-caps style). */
export const labelClass = "label-caps mb-1 block";

/** Muted helper line under a field. */
export const hintClass = "mt-1 text-xs text-ink-400";

/** Inline error/alert text. */
export const errorClass =
  "rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400";

/** Inline success/notice text. */
export const noticeClass =
  "rounded-sm border border-olive-500/60 bg-olive-400/10 px-3 py-2 text-sm text-olive-400";
