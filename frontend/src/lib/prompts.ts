/**
 * Prompt Library client.
 *
 * Stage 1 has two modes. *Advanced* is prompt-first: the operator writes the
 * generation prompts, then collects the images those prompts produced and binds
 * them back. This module is the typed client for that side of the stage.
 *
 * Kept out of `lib/api.ts` for the same reason `lib/settings.ts` is: a feature
 * module should not force every importer to pull in the whole stage API
 * surface.
 */

import { api } from "./client";

/** Library state of a prompt. */
export type PromptStatus = "DRAFT" | "USED" | "ARCHIVED";

export interface Prompt {
  id: string;
  title: string;
  body: string;
  negative_prompt: string | null;
  /** Generator-specific settings, e.g. `{ model, aspect, seed }`. */
  params: Record<string, unknown> | null;
  tags: string[] | null;
  status: PromptStatus;
  used_at: string | null;
  created_at: string;
  updated_at: string;
  /** How many image records are currently bound to this prompt. */
  bound_count: number;
}

export interface PromptListResponse {
  items: Prompt[];
  total: number;
  used: number;
  unused: number;
}

export interface PromptBindResponse {
  updated: number;
  missing: string[];
  /** Records that were bound to a *different* prompt and got re-pointed. */
  rebound: string[];
  prompt: Prompt;
}

/** Filter for the prompt list. `unused` means "no image bound yet". */
export type PromptFilter = "all" | "draft" | "used" | "unused" | "archived";

export interface PromptDraft {
  title?: string;
  body: string;
  negative_prompt?: string;
  tags?: string[];
  params?: Record<string, unknown>;
  status?: PromptStatus;
}

export async function fetchPrompts(
  status: PromptFilter = "all"
): Promise<PromptListResponse> {
  const { data } = await api.get<PromptListResponse>("/api/prompts", {
    params: { status },
  });
  return data;
}

export async function createPrompt(draft: PromptDraft): Promise<Prompt> {
  const { data } = await api.post<Prompt>("/api/prompts", draft);
  return data;
}

export async function updatePrompt(
  id: string,
  patch: Partial<PromptDraft>
): Promise<Prompt> {
  const { data } = await api.patch<Prompt>(`/api/prompts/${id}`, patch);
  return data;
}

export async function deletePrompt(
  id: string
): Promise<{ deleted: number; unbound: number }> {
  const { data } = await api.delete<{ deleted: number; unbound: number }>(
    `/api/prompts/${id}`
  );
  return data;
}

/**
 * Bind images to a prompt, or unbind them.
 *
 * Binding is many-to-one — one prompt, many images — so re-binding an image
 * that already belongs to another prompt re-points it.
 */
export async function bindPrompt(
  promptId: string,
  recordIds: string[],
  unbind = false
): Promise<PromptBindResponse> {
  const { data } = await api.post<PromptBindResponse>(
    `/api/prompts/${promptId}/bind`,
    { record_ids: recordIds, unbind }
  );
  return data;
}

/** Longest title the backend stores, mirrored so the editor can cap input. */
export const PROMPT_TITLE_MAX = 200;

/**
 * Derive a display title from a prompt body's first line.
 *
 * Mirrors `services/prompt_library.derive_title` so the sidebar can show a
 * title for an unsaved prompt block without a round trip. The backend remains
 * authoritative and fills in the same value when the title is left blank.
 */
export function derivePromptTitle(
  body: string,
  fallback = "Untitled prompt"
): string {
  const text = (body ?? "").trim();
  if (!text) return fallback;

  const firstLine = text.split("\n").find((line) => line.trim()) ?? "";
  const sentence = firstLine.replace(/\s+/g, " ").trim().split(". ")[0].trim();
  if (!sentence) return fallback;
  if (sentence.length <= PROMPT_TITLE_MAX) return sentence;
  return `${sentence.slice(0, PROMPT_TITLE_MAX - 1).trimEnd()}…`;
}
