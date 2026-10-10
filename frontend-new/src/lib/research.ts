/**
 * Prompt Research — the typed client and event vocabulary for `/prompts`.
 *
 * One module for the feature's whole wire surface (runs, system prompts,
 * priority sources) because the page edits them together as one workspace.
 * Mirrors `backend/routers/research.py` and `backend/schemas.py`.
 *
 * The event types are a *contract*: the stream reducer switches on them, so
 * `parseEvent` rejects an unknown `type` rather than letting an unhandled shape
 * into state where it would silently do nothing.
 */
import { api, API_BASE_URL } from "./client";

/** The three canonical research objectives. Legacy ids normalise to these. */
export type ResearchMode = "generate" | "research" | "ideas";

/**
 * Display/key normaliser for a stored run's mode.
 *
 * Old runs say `static`/`batch`; the backend maps both onto `generate`, and so
 * does this — one helper so the sidebar badge, the mode selector and the
 * reopened run's settings can never disagree about what a run is.
 */
export function normalizeMode(mode: string | null | undefined): ResearchMode {
  const key = (mode ?? "").trim().toLowerCase();
  if (key === "research" || key === "ideas") return key;
  return "generate";
}

export interface ResearchModeSpec {
  id: ResearchMode;
  label: string;
  tagline: string;
  description: string;
  produces_prompts: boolean;
  researches: boolean;
  supports_count: boolean;
  supports_validity: boolean;
}

export interface ResearchSettings {
  modes: ResearchModeSpec[];
  max_prompts: number;
  max_tool_calls: number;
  disclaimer: string;
  context_window: number;
  keep_recent_turns: number;
  compact_at_share: number;
  warn_at_share: number;
  target_average: number;
}

export type ResearchRunStatus = "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface ResearchMessage {
  role: string;
  content: string;
  created_at?: string;
}

export interface ResearchSource {
  title: string;
  url: string;
  snippet?: string;
  display_url?: string;
}

export interface ResearchPrompt {
  body: string;
  index: number;
  title?: string;
  tags?: string[];
  category?: number | null;
  category_name?: string;
  notes?: string;
  warnings: string[];
  duplicate_of: number | null;
  duplicate: boolean;
  chars: number;
}

export interface ResearchValidity {
  customer_download_confidence: number;
  adobe_acceptance_confidence: number;
  collective_average: number;
  collective_band: "strong" | "moderate" | "weak" | "unknown";
  collective_label: string;
  download_band: string;
  acceptance_band: string;
  recommendation: string;
  reasoning: string;
  evidence: string[];
  /** The idea these scores describe — without it the numbers read as generic. */
  subject: string;
  target_average: number;
  /**
   * Whether the idea reached the target. Optional because the backend derives
   * it; `null` must render as "unknown", never as a confident verdict.
   */
  meets_target?: boolean | null;
  disclaimer: string;
}

export interface FollowUpAction {
  id: string;
  label: string;
  /** The message to send when the button is pressed — never hard-coded in the UI. */
  message: string;
}

/** One streamed event. `type` is the discriminant. */
export type ResearchEvent =
  | { type: "run_started"; mode?: string; count?: number }
  | { type: "thinking"; text: string }
  | { type: "message"; text: string }
  | {
      type: "tool_call";
      name: string;
      arguments: Record<string, unknown>;
      summary: string;
    }
  | {
      type: "tool_result";
      name: string;
      summary: string;
      ok: boolean;
      duration_seconds?: number;
    }
  | { type: "sources"; sources: ResearchSource[] }
  | {
      type: "prompts";
      prompts: ResearchPrompt[];
      summary?: string;
      saveable?: string[];
    }
  | { type: "validity"; validity: ResearchValidity; follow_up_actions?: FollowUpAction[] }
  | { type: "context" }
  | { type: "notice"; text: string }
  | { type: "error"; text: string }
  | { type: "run_finished"; status: string; answer?: string };

export interface ResearchRun {
  id: string;
  title: string;
  seed_message: string;
  mode: string;
  status: ResearchRunStatus;
  messages: ResearchMessage[];
  events: ResearchEvent[];
  result: Record<string, unknown>;
  settings: Record<string, unknown>;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchRunSummary {
  id: string;
  title: string;
  seed_message: string;
  mode: string;
  status: ResearchRunStatus;
  error: string | null;
  created_at: string;
  updated_at: string;
  prompt_count: number;
  has_validity: boolean;
}

/** Event types this client understands, mirroring the backend vocabulary. */
const KNOWN_EVENT_TYPES = new Set([
  "run_started",
  "thinking",
  "message",
  "tool_call",
  "tool_result",
  "sources",
  "prompts",
  "validity",
  "context",
  "notice",
  "error",
  "run_finished",
]);

/**
 * Validate a decoded event. An unrecognised `type` is dropped rather than
 * stored — an unknown shape in state would crash or silently ignore the
 * reducer, and the UI would look like it had stopped responding.
 */
export function parseEvent(raw: unknown): ResearchEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const type = (raw as { type?: unknown }).type;
  if (typeof type !== "string" || !KNOWN_EVENT_TYPES.has(type)) return null;
  return raw as ResearchEvent;
}

// --------------------------------------------------------------------------- //
// Conversations
// --------------------------------------------------------------------------- //

export async function fetchResearchSettings(): Promise<ResearchSettings> {
  const { data } = await api.get<ResearchSettings>("/api/research/settings");
  return data;
}

export async function fetchResearchRuns(limit = 50): Promise<ResearchRunSummary[]> {
  const { data } = await api.get<{ items: ResearchRunSummary[]; total: number }>(
    "/api/research/runs",
    { params: { limit } }
  );
  return data.items;
}

export async function fetchResearchRun(runId: string): Promise<ResearchRun> {
  const { data } = await api.get<ResearchRun>(`/api/research/runs/${runId}`);
  return data;
}

export interface StartRunInput {
  message: string;
  mode: ResearchMode;
  count: number;
  validityCheck: boolean;
}

/**
 * Create a conversation **without** running its opening turn (`stream_first`),
 * so the caller can stream it and the operator watches the agent work from the
 * first second instead of waiting on a buffered response.
 */
export async function createResearchRun(input: StartRunInput): Promise<ResearchRun> {
  const { data } = await api.post<ResearchRun>("/api/research/runs", {
    message: input.message,
    mode: input.mode,
    count: input.count,
    validity_check: input.validityCheck,
    stream_first: true,
  });
  return data;
}

/** Per-prompt metadata sent with an acceptance so titles/tags/categories land. */
export interface AcceptPromptDetail {
  title?: string;
  tags?: string[];
  category?: number | null;
}

export interface AcceptResult {
  created: Array<{ id: string; title: string; body: string }>;
  skipped: string[];
  count: number;
}

export async function acceptResearchPrompts(
  runId: string,
  prompts: string[],
  options: {
    tags?: string[];
    negativePrompt?: string;
    /** Positionally matches `prompts`. */
    details?: AcceptPromptDetail[];
  } = {}
): Promise<AcceptResult> {
  const { data } = await api.post<AcceptResult>(`/api/research/runs/${runId}/accept`, {
    prompts,
    tags: options.tags,
    negative_prompt: options.negativePrompt,
    details: options.details,
  });
  return data;
}

export async function deleteResearchRun(runId: string): Promise<void> {
  await api.delete(`/api/research/runs/${runId}`);
}

/**
 * The SSE stream URL for one turn.
 *
 * Built here (not with the axios instance) because the transport is
 * `fetch` + reader, not `EventSource` — `EventSource` reconnects on any
 * disconnect, including a normal end of stream, which would re-run every web
 * search. `message` is omitted for the opening turn: the backend reads the
 * stored user turn, so the question is not appended twice.
 */
export function researchStreamUrl(
  runId: string,
  options: { message?: string; count?: number; validityCheck?: boolean }
): string {
  const params = new URLSearchParams();
  if (options.message) params.set("message", options.message);
  if (options.count != null) params.set("count", String(options.count));
  if (options.validityCheck != null) {
    params.set("validity_check", String(options.validityCheck));
  }
  const query = params.toString();
  return `${API_BASE_URL}/api/research/runs/${runId}/stream${query ? `?${query}` : ""}`;
}

// --------------------------------------------------------------------------- //
// Per-mode system prompts
// --------------------------------------------------------------------------- //

export type SystemPromptMode = ResearchMode;

export interface SystemPromptsDoc {
  /** Effective text per mode (saved edit or shipped default). */
  items: Record<string, string>;
  defaults: Record<string, string>;
  is_custom: Record<string, boolean>;
}

export async function fetchSystemPrompts(): Promise<SystemPromptsDoc> {
  const { data } = await api.get<SystemPromptsDoc>("/api/research/system-prompts");
  return data;
}

/** Replace one mode's text. `text: ""` restores the shipped default. */
export async function saveSystemPrompt(
  mode: SystemPromptMode,
  text: string
): Promise<SystemPromptsDoc> {
  const { data } = await api.put<SystemPromptsDoc>("/api/research/system-prompts", {
    mode,
    text,
  });
  return data;
}

// --------------------------------------------------------------------------- //
// Priority sources (the operator's own list of sites the agent should prefer)
// --------------------------------------------------------------------------- //

export interface PrioritySource {
  url: string;
  name: string;
  priority: number;
  notes: string;
  tags: string[];
}

export interface PrioritySourceFile {
  version?: number;
  sources: PrioritySource[];
  /** Non-fatal remarks from the parser: entries dropped, fields trimmed. */
  warnings: string[];
  /** The uploaded file's name, for display. Empty when none is stored. */
  filename: string;
  template_version?: number;
}

export async function fetchPrioritySources(): Promise<PrioritySourceFile> {
  const { data } = await api.get<PrioritySourceFile>("/api/research/sources");
  return data;
}

/**
 * Upload a source file's *text*. Sent verbatim so the server is the only thing
 * that decides validity — a client that parsed first would let a malformed file
 * look like a successful upload that silently did nothing.
 */
export async function uploadPrioritySources(
  content: string,
  filename: string
): Promise<PrioritySourceFile> {
  const { data } = await api.post<PrioritySourceFile>("/api/research/sources", {
    content,
    filename,
  });
  return data;
}

export async function clearPrioritySources(): Promise<PrioritySourceFile> {
  const { data } = await api.delete<PrioritySourceFile>("/api/research/sources");
  return data;
}

/**
 * Download the template by fetching it and clicking a synthetic anchor.
 *
 * Not a plain `<a download>`: the app and the API are different origins, and a
 * cross-origin `download` attribute is ignored — the file would open in a tab
 * instead of saving.
 */
export async function downloadSourceTemplate(): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/research/sources/template`);
  if (!response.ok) {
    throw new Error(`Could not download the template (HTTP ${response.status}).`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "research-priority-sources.json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    // Revoked on the next tick: revoking synchronously can cancel the download.
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

/** The host of a source URL, for compact display ("stock.adobe.com"). */
export function sourceHost(source: PrioritySource): string {
  try {
    return new URL(source.url).hostname.replace(/^www\./, "");
  } catch {
    return source.url;
  }
}
