/**
 * Acceptance-issue vocabulary, mirrored from the backend.
 *
 * The backend owns the authoritative lists in
 * `backend/services/acceptance/types.py`. This module mirrors them for the UI
 * because a persisted `acceptance_report` is a *snapshot*: its `refinable` flag
 * records what the code knew at the moment the report was written. When the
 * engine gains a new capability, every report already on disk still carries the
 * old flag — so an issue the pipeline can now fix would keep rendering without
 * its "auto-fixable" badge until the image happened to be re-scored.
 *
 * Deriving the badge from this list instead keeps the UI honest for old and new
 * reports alike.
 *
 * NOTE: keep in sync with `REFINABLE_CODES`, `CONTAINER_FIXABLE_CODES`, and
 * `MANUAL_ONLY_CODES` in the backend. `test_issue_vocabulary` in the backend
 * suite fails if the two drift apart.
 */

/** Pixel-level corrections the Stage 4 recipe can apply. */
export const PIXEL_FIXABLE_CODES = [
  "highlights_clipped",
  "shadows_crushed",
  "overall_oversaturated",
  "skin_tone_cast",
  "neon_greens",
  "edge_halo",
  "chroma_fringe",
  "soft_focus",
  "flat_synthetic_texture",
  "excessive_noise",
] as const;

/**
 * Container-level corrections: the sRGB colour profile.
 *
 * The colour space is a property of the file's encoding rather than of its
 * pixel values, so the pixel recipe cannot touch it — but the auto-fix engine
 * converts or re-tags the file, which makes it fully automatic.
 */
export const CONTAINER_FIXABLE_CODES = ["not_srgb"] as const;

/** Everything the auto-fix engine can correct without human input. */
export const AUTOFIXABLE_CODES: readonly string[] = [
  ...PIXEL_FIXABLE_CODES,
  ...CONTAINER_FIXABLE_CODES,
];

/** Issues that need a human decision and can never be auto-fixed. */
export const MANUAL_ONLY_CODES = [
  "wrong_format",
  "low_resolution",
  "excessive_resolution",
  "file_too_large",
  "semantic_flagged",
  "hallucinated_text",
  "possible_ip",
] as const;

const AUTOFIXABLE_SET = new Set(AUTOFIXABLE_CODES);

/** True when the auto-fix engine can correct this issue code. */
export function isAutoFixable(code: string): boolean {
  return AUTOFIXABLE_SET.has(code);
}

/** Short, operator-facing names for each issue code. */
export const ISSUE_LABELS: Record<string, string> = {
  not_srgb: "sRGB colour profile",
  wrong_format: "JPEG format",
  overall_oversaturated: "Global saturation",
  skin_tone_cast: "Skin-tone cast",
  neon_greens: "Oversaturated greens",
  highlights_clipped: "Clipped highlights",
  shadows_crushed: "Crushed shadows",
  edge_halo: "Edge halo",
  chroma_fringe: "Chromatic aberration",
  soft_focus: "Soft focus",
  flat_synthetic_texture: "Synthetic texture",
  excessive_noise: "Excessive noise",
  semantic_flagged: "Semantic flag",
  hallucinated_text: "Embedded text",
  possible_ip: "Possible IP / logo",
  low_resolution: "Resolution too low",
  excessive_resolution: "Resolution too high",
  file_too_large: "File too large",
};

/** Human label for an issue code, falling back to the raw code. */
export function issueLabel(code: string): string {
  return ISSUE_LABELS[code] ?? code;
}

/**
 * The auto-fixable codes present in a report.
 *
 * Reads the report's own issues (which are always current) rather than its
 * cached `refinable_codes` array, then filters by this module's vocabulary.
 */
export function autoFixableCodesIn(issues: { code: string }[]): string[] {
  return Array.from(
    new Set(issues.filter((issue) => isAutoFixable(issue.code)).map((i) => i.code))
  );
}
