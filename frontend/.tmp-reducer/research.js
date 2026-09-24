"use strict";
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
Object.defineProperty(exports, "__esModule", { value: true });
exports.parseEvent = parseEvent;
exports.fetchResearchSettings = fetchResearchSettings;
exports.fetchResearchRuns = fetchResearchRuns;
exports.fetchResearchRun = fetchResearchRun;
exports.startResearchRun = startResearchRun;
exports.createResearchRun = createResearchRun;
exports.sendResearchMessage = sendResearchMessage;
exports.acceptResearchPrompts = acceptResearchPrompts;
exports.deleteResearchRun = deleteResearchRun;
exports.researchStreamUrl = researchStreamUrl;
const client_1 = require("./client");
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
    "context",
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
function parseEvent(raw) {
    if (!raw || typeof raw !== "object")
        return null;
    const type = raw.type;
    if (typeof type !== "string" || !KNOWN_EVENT_TYPES.has(type))
        return null;
    return raw;
}
// --------------------------------------------------------------------------- //
// REST client
// --------------------------------------------------------------------------- //
async function fetchResearchSettings() {
    const { data } = await client_1.api.get("/api/research/settings");
    return data;
}
async function fetchResearchRuns(limit = 50) {
    const { data } = await client_1.api.get("/api/research/runs", { params: { limit } });
    return data.items;
}
async function fetchResearchRun(runId) {
    const { data } = await client_1.api.get(`/api/research/runs/${runId}`);
    return data;
}
async function startResearchRun(input) {
    const { data } = await client_1.api.post("/api/research/runs", {
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
async function createResearchRun(input) {
    const { data } = await client_1.api.post("/api/research/runs", {
        message: input.message,
        mode: input.mode,
        count: input.count,
        style_instruction: input.styleInstruction,
        validity_check: input.validityCheck,
        stream_first: true,
    });
    return data;
}
async function sendResearchMessage(runId, message) {
    const { data } = await client_1.api.post(`/api/research/runs/${runId}/messages`, { message });
    return data;
}
async function acceptResearchPrompts(runId, prompts, options = {}) {
    const { data } = await client_1.api.post(`/api/research/runs/${runId}/accept`, {
        prompts,
        tags: options.tags,
        negative_prompt: options.negativePrompt,
        details: options.details,
    });
    return data;
}
async function deleteResearchRun(runId) {
    await client_1.api.delete(`/api/research/runs/${runId}`);
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
function researchStreamUrl(runId, options) {
    const params = new URLSearchParams();
    if (options.message)
        params.set("message", options.message);
    if (options.count != null)
        params.set("count", String(options.count));
    if (options.validityCheck != null) {
        params.set("validity_check", String(options.validityCheck));
    }
    const query = params.toString();
    return `${client_1.API_BASE_URL}/api/research/runs/${runId}/stream${query ? `?${query}` : ""}`;
}
