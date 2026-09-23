/**
 * Prompt Research — the typed client and event vocabulary.
 *
 * Kept out of `lib/api.ts` for the same reason `lib/settings.ts` and
 * `lib/prompts.ts` are: a feature module should not force every importer to pull
 * in the whole stage API surface.
 *
 * The event types mirror `backend/services/research/events.py`. They are a
 * *contract*, not a suggestion: the stream reducer switches on them, so a new
 * backend event that the UI does not know about is dropped silently. The
 * `parseEvent` guard below rejects an unknown type rather than letting it into
 * state, which makes that visible instead of mysterious.
 */

import { api, API_BASE_URL } from "./client";

/** The four research objectives. */
export type ResearchMode = "static" | "batch" | "research" | "ideas";

export interface ResearchModeSpec {
  id: ResearchMode;
  label: string;
  tagline: string;
  description: string;
  /** Whether the mode ends with concrete prompts. */
  produces_prompts: boolean;
  /** Whether the mode uses the web tools. */
  researches: boolean;
  supports_count: boolean;
  supports_validity: boolean;
}

export interface ResearchSettings {
  modes: ResearchModeSpec[];
  /** The operator's house standard, editable per run. */
  default_style_instruction: string;
  house_rules: string;
  max_prompts: number;
  max_tool_calls: number;
  disclaimer: string;
}

export type ResearchRunStatus = "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface ResearchSource {
  title: string;
  url: string;
  snippet?: string;
  display_url?: string;
}

export interface ResearchPrompt {
  body: string;
  index: number;
  /** The model's own short label, empty when it did not supply one. */
  title?: string;
  /** Topical tags from the JSON contract. */
  tags?: string[];
  /** Adobe's numeric category code, or null when the model gave none. */
  category?: number | null;
  /** The category's human name, resolved by the backend. */
  category_name?: string;
  /** A one-line note for the operator. */
  notes?: string;
  warnings: string[];
  /** The 1-based index of the prompt this one duplicates, or null. */
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
  /** Always present: states the scores are a judgement, not a measurement. */
  disclaimer: string;
}

export interface ResearchToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface ResearchResult {
  prompts?: ResearchPrompt[];
  sources?: ResearchSource[];
  validity?: ResearchValidity | null;
  notices?: string[];
  tool_calls?: ResearchToolCall[];
  thinking?: string;
  accepted_prompt_ids?: string[];
}

export interface ResearchMessage {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
}

/** One streamed event. `type` is the discriminant. */
export type ResearchEvent =
  | { type: "run_started"; mode: string; count?: number; tools?: string[]; max_tool_calls?: number }
  | { type: "thinking"; text: string }
  | { type: "message"; text: string }
  | { type: "tool_call"; name: string; arguments: Record<string, unknown>; summary: string }
  | { type: "tool_result"; name: string; summary: string; ok: boolean; duration_seconds?: number }
  | { type: "sources"; sources: ResearchSource[] }
  | { type: "prompts"; prompts: ResearchPrompt[]; summary?: string; duplicate_pairs?: unknown[]; saveable?: string[] }
  | { type: "validity"; validity: ResearchValidity; follow_up_actions?: FollowUpAction[] }
  | { type: "notice"; text: string }
  | { type: "error"; text: string }
  | { type: "run_finished"; status: string; answer?: string; thinking?: string };

export interface FollowUpAction {
  id: string;
  label: string;
  /** The message to send when the button is pressed. */
  message: string;
}

export interface ResearchRun {
  id: string;
  title: string;
  seed_message: string;
  mode: string;
  status: ResearchRunStatus;
  messages: ResearchMessage[];
  events: ResearchEvent[];
  result: ResearchResult;
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

/** The event types this client understands, mirroring the backend vocabulary. */
const KNOWN_EVENT_TYPES = new Set([
  "run_started",
  "thinking",
  "message",
  "tool_call",
  "tool_result",
  "sources",
  "prompts",
  "validity",
  "notice",
  "error",
  "run_finished",
]);

/**
 * Validate a decoded event.
 *
 * An unrecognised `type` is dropped rather than stored. Storing it would put an
 * unknown shape into state, where the reducer would either crash or — worse —
 * silently ignore it, and the UI would look like it had simply stopped
 * responding to the agent.
 */
export function parseEvent(raw: unknown): ResearchEvent | null {
  if (!raw || typeof raw !== "object") return null;
  const type = (raw as { type?: unknown }).type;
  if (typeof type !== "string" || !KNOWN_EVENT_TYPES.has(type)) return null;
  return raw as ResearchEvent;
}

// --------------------------------------------------------------------------- //
// REST client
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
  styleInstruction: string;
  validityCheck: boolean;
}

export async function startResearchRun(input: StartRunInput): Promise<ResearchRun> {
  const { data } = await api.post<ResearchRun>("/api/research/runs", {
    message: input.message,
    mode: input.mode,
    count: input.count,
    style_instruction: input.styleInstruction,
    validity_check: input.validityCheck,
  });
  return data;
}

/**
 * Create a conversation **without** running its opening turn.
 *
 * The research page then streams that turn, so the operator watches the agent
 * work from the first second. The buffered `startResearchRun` above is kept for
 * scripted callers and tests, where a single response is more convenient.
 */
export async function createResearchRun(input: StartRunInput): Promise<ResearchRun> {
  const { data } = await api.post<ResearchRun>("/api/research/runs", {
    message: input.message,
    mode: input.mode,
    count: input.count,
    style_instruction: input.styleInstruction,
    validity_check: input.validityCheck,
    stream_first: true,
  });
  return data;
}

export async function sendResearchMessage(
  runId: string,
  message: string
): Promise<ResearchRun> {
  const { data } = await api.post<ResearchRun>(
    `/api/research/runs/${runId}/messages`,
    { message }
  );
  return data;
}

export async function acceptResearchPrompts(
  runId: string,
  prompts: string[],
  options: {
    tags?: string[];
    negativePrompt?: string;
    /**
     * Per-prompt metadata, positionally matching `prompts`. Sent so the title,
     * tags and category the model supplied reach the library instead of being
     * discarded at the last step.
     */
    details?: Array<{ title?: string; tags?: string[]; category?: number | null }>;
  } = {}
): Promise<{ created: unknown[]; skipped: string[]; count: number }> {
  const { data } = await api.post(`/api/research/runs/${runId}/accept`, {
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
 * The URL of the streaming endpoint.
 *
 * Built here rather than with the axios instance because `EventSource` cannot be
 * given a POST body or custom headers — the message travels as a query
 * parameter. `api`'s base URL is reused so the two paths cannot point at
 * different backends.
 *
 * `message` is omitted for the opening turn of a newly created conversation: the
 * backend reads the stored user turn instead, so the question is not appended to
 * the transcript twice.
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
