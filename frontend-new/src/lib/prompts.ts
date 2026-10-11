/**
 * Prompt Library client for the `/prompts` pages.
 *
 * The library is filtered on one axis — **status** (`used` / `unused` /
 * `archived` read `Prompt.status`, `draft` is the server's alias for the same
 * state the UI labels "Unused"). The server still reports binding counts on
 * each prompt and in the listing totals; the UI deliberately ignores them.
 *
 * The server filters (`GET /api/prompts?status=&q=`) and reports the counts,
 * so a tab count never has to be derived client-side.
 *
 * Kept out of a shared api module so this feature cannot force every importer
 * to pull the whole stage API surface.
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
  /** Folder name (batch grouping); null when ungrouped. */
  group_name: string | null;
}

/** Folder (group) name + how many prompts it holds, busiest first. */
export interface PromptGroup {
  name: string;
  count: number;
}

export interface PromptListResponse {
  items: Prompt[];
  total: number;
  used: number;
  unused: number;
  /**
   * Binding-axis totals. Still sent by the server; the UI no longer renders
   * a Bound/Unbound filter, so nothing reads these.
   */
  bound: number;
  unbound: number;
  archived: number;
  /** Folders derived from group_name, for the filter chips. */
  groups: PromptGroup[];
}

/**
 * Server-side list filter. `all` matches everything; `draft` is the server's
 * name for the same state the UI labels "Unused".
 */
export type PromptFilter = "all" | "draft" | "used" | "unused" | "archived";

/**
 * Fetch prompts. `status` filters one axis, `q` is a case-insensitive substring
 * search over title, body, negative prompt and tags, `group` narrows to one
 * folder (empty matches everything) — the server composes them.
 */
export async function fetchPrompts(
  status: PromptFilter = "all",
  q = "",
  group = ""
): Promise<PromptListResponse> {
  const { data } = await api.get<PromptListResponse>("/api/prompts", {
    params: { status, q: q || undefined, group: group || undefined },
  });
  return data;
}

/** Response of the bulk folder assignment. */
export interface PromptGroupAssignResponse {
  updated: number;
  /** Ids the server did not recognise (reported, never fatal). */
  missing: string[];
  /** The folder the prompts landed in; null when ungrouped. */
  group_name: string | null;
}

/**
 * Add (or remove, with `groupName = ""`) many prompts from a folder in one
 * round trip — the batch-use flow: select the prompts, name the folder once.
 */
export async function assignPromptGroup(
  promptIds: string[],
  groupName: string
): Promise<PromptGroupAssignResponse> {
  const { data } = await api.post<PromptGroupAssignResponse>("/api/prompts/group", {
    prompt_ids: promptIds,
    group_name: groupName,
  });
  return data;
}

/** Partial update; omitted fields are left untouched. */
export async function updatePrompt(
  id: string,
  patch: Partial<{ status: PromptStatus; title: string; body: string; tags: string[] }>
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
 * Copy text to the clipboard, with a textarea fallback for non-secure contexts
 * (`navigator.clipboard` is unavailable on plain-HTTP origins other than
 * localhost).
 *
 * Returns false on failure so the caller can say "copy blocked" instead of
 * showing a success tick the operator will not get.
 */
export async function copyText(value: string): Promise<boolean> {
  const text = value ?? "";
  if (!text) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Fall through to the legacy path.
  }
  try {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    const ok = document.execCommand("copy");
    textarea.remove();
    return ok;
  } catch {
    return false;
  }
}
