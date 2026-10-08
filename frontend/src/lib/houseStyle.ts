/**
 * House style — the operator's house standard and house rules, persisted server-side.
 *
 * These two texts used to be React state seeded from a constant, which is why an
 * edit vanished on reload: nothing ever wrote them anywhere except as a side
 * effect of *starting a run*. This module is the client for the persisted
 * resource, so editing the standard is an action in its own right.
 *
 * Kept out of `lib/research.ts` because it is a separate lifecycle: the research
 * vocabulary is read once per page mount and never written, while this is read
 * and written on every save. A page that never edits its style should not pull
 * the write path in.
 */

import { api } from "./client";

/** The operator's house standard and rules, as the server would use them now. */
export interface HouseStyle {
  /** The house standard applied to a run that does not override it. */
  style_instruction: string;
  /** The non-negotiable constraints block pasted into the system prompt. */
  house_rules: string;
  /**
   * Whether the operator wrote this, rather than it being the shipped default.
   *
   * Server-derived, not a client comparison: it decides whether Reset is
   * meaningful, and a client-side compare against a separately-fetched constant
   * is how Reset ends up offering to restore something already restored.
   */
  style_is_custom: boolean;
  rules_is_custom: boolean;
}

/** Partial update. Omitted fields are untouched; `""` restores the default. */
export interface HouseStyleUpdate {
  style_instruction?: string;
  house_rules?: string;
}

/**
 * Fetch the saved house style.
 *
 * Separate from `fetchResearchSettings` even though the settings response also
 * carries both texts: that endpoint is page vocabulary and is read once, while
 * this is a resource with a write path, and coupling them would mean every save
 * had to first wait for — and could clobber — the vocabulary fetch.
 */
export async function fetchHouseStyle(): Promise<HouseStyle> {
  const { data } = await api.get<HouseStyle>("/api/research/style");
  return data;
}

/**
 * Save one or both fields, returning what the server stored.
 *
 * The response replaces local state rather than being assumed equal to it: the
 * server strips whitespace and restores defaults for blank values, so echoing the
 * submitted text back would show the operator something that is not what runs
 * will actually use.
 */
export async function saveHouseStyle(
  payload: HouseStyleUpdate
): Promise<HouseStyle> {
  const { data } = await api.put<HouseStyle>("/api/research/style", payload);
  return data;
}

/** Restore both the house standard and the rules to the shipped defaults. */
export async function resetHouseStyle(): Promise<HouseStyle> {
  const { data } = await api.delete<HouseStyle>("/api/research/style");
  return data;
}