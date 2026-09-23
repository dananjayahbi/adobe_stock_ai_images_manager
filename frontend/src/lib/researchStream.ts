/**
 * The stream reducer: folds research events into the state the UI renders.
 *
 * Kept as a pure function, separate from the hook that feeds it, for three
 * reasons:
 *
 * * the live view, the replayed transcript and a unit test all go through the
 *   *same* code, so they cannot disagree about what a run produced;
 * * a reload replays the stored events through this reducer, so the restored
 *   view is derived from the same rules as the live one;
 * * a bug in the reducer is testable without a browser or a socket.
 *
 * The state is deliberately *accumulated*, never recomputed: events arrive
 * incrementally, and the answer is the concatenation of many `message` chunks.
 */

import type {
  FollowUpAction,
  ResearchEvent,
  ResearchPrompt,
  ResearchSource,
  ResearchValidity,
} from "./research";

export interface ToolStep {
  /** Stable key for React; the index is enough because steps are append-only. */
  id: number;
  name: string;
  arguments: Record<string, unknown>;
  summary: string;
  /** Filled in when the matching `tool_result` arrives. */
  result?: { summary: string; ok: boolean; durationSeconds?: number };
}

export interface ResearchStreamState {
  /** The model's reasoning, streamed live and rendered collapsed. */
  thinking: string;
  /** The model's visible prose, streamed live. */
  message: string;
  /** The final answer, once the run's terminal event arrives. */
  answer: string;
  steps: ToolStep[];
  sources: ResearchSource[];
  prompts: ResearchPrompt[];
  /** The model's own one-line statement of what it produced, from the JSON. */
  promptSummary: string;
  validity: ResearchValidity | null;
  followUpActions: FollowUpAction[];
  notices: string[];
  error: string;
  /** True between the request starting and a terminal event arriving. */
  isStreaming: boolean;
  /** Set when the terminal event arrives, so the UI can stop its spinner. */
  finished: boolean;
  /** The mode and tool list the run actually used. */
  mode: string;
  tools: string[];
  maxToolCalls: number;
}

export function initialState(): ResearchStreamState {
  return {
    thinking: "",
    message: "",
    answer: "",
    steps: [],
    sources: [],
    prompts: [],
    promptSummary: "",
    validity: null,
    followUpActions: [],
    notices: [],
    error: "",
    isStreaming: false,
    finished: false,
    mode: "",
    tools: [],
    maxToolCalls: 0,
  };
}

/** Merge sources, de-duplicated by URL and in first-seen order.
 *
 * A source is often returned by more than one query; listing it twice would make
 * a single page look like two independent confirmations. The backend
 * accumulator does the same, so the live view and the replayed view agree.
 */
function mergeSources(
  existing: ResearchSource[],
  incoming: ResearchSource[]
): ResearchSource[] {
  const seen = new Set(existing.map((source) => source.url));
  const merged = [...existing];
  for (const source of incoming) {
    if (!source?.url || seen.has(source.url)) continue;
    seen.add(source.url);
    merged.push(source);
  }
  return merged;
}

export function reduceEvent(
  state: ResearchStreamState,
  event: ResearchEvent
): ResearchStreamState {
  switch (event.type) {
    case "run_started":
      return {
        ...state,
        mode: event.mode ?? state.mode,
        tools: event.tools ?? state.tools,
        maxToolCalls: event.max_tool_calls ?? state.maxToolCalls,
      };

    case "thinking":
      return { ...state, thinking: state.thinking + event.text };

    case "message":
      return { ...state, message: state.message + event.text };

    case "tool_call":
      return {
        ...state,
        steps: [
          ...state.steps,
          {
            id: state.steps.length,
            name: event.name,
            arguments: event.arguments ?? {},
            summary: event.summary,
          },
        ],
      };

    case "tool_result": {
      // Attach to the *last step with this tool name that has no result yet*,
      // not simply the last step: a model may call two tools in one turn and the
      // results arrive in order, so matching by name keeps each summary with its
      // own call.
      const steps = [...state.steps];
      for (let index = steps.length - 1; index >= 0; index -= 1) {
        if (steps[index].name === event.name && !steps[index].result) {
          steps[index] = {
            ...steps[index],
            result: {
              summary: event.summary,
              ok: event.ok,
              durationSeconds: event.duration_seconds,
            },
          };
          break;
        }
      }
      return { ...state, steps };
    }

    case "sources":
      return { ...state, sources: mergeSources(state.sources, event.sources ?? []) };

    case "prompts":
      return {
        ...state,
        prompts: event.prompts ?? [],
        promptSummary: event.summary?.trim() ?? "",
      };

    case "validity":
      return {
        ...state,
        validity: event.validity ?? null,
        followUpActions: event.follow_up_actions ?? state.followUpActions,
      };

    case "notice":
      // Deduplicated: a repeated notice would stack the same banner.
      return state.notices.includes(event.text)
        ? state
        : { ...state, notices: [...state.notices, event.text] };

    case "error":
      return { ...state, error: event.text, finished: true, isStreaming: false };

    case "run_finished":
      return {
        ...state,
        answer: event.answer?.trim() || state.message.trim(),
        isStreaming: false,
        finished: true,
      };

    default:
      return state;
  }
}

/** Fold a whole event list. Used when replaying a stored conversation. */
export function reduceEvents(events: ResearchEvent[]): ResearchStreamState {
  return events.reduce(reduceEvent, initialState());
}

/**
 * The prompts the UI pre-selects for saving.
 *
 * Duplicates are excluded: the default action should not create the
 * near-identical pair Adobe refuses. They are still *shown*, with a warning,
 * because the operator may disagree with the similarity call.
 */
export function saveablePrompts(prompts: ResearchPrompt[]): string[] {
  return prompts.filter((prompt) => !prompt.duplicate).map((prompt) => prompt.body);
}

/**
 * A one-line description of what the agent is doing right now.
 *
 * The composer used to say only "The agent is working", which is indistinguishable
 * from a hung request during a turn that can legitimately run for a minute. This
 * reports the observable facts the stream already carries — which tool is running,
 * whether anything has been written yet — so the spinner never stands alone.
 */
export function activityLine(state: ResearchStreamState): string {
  const pending = [...state.steps].reverse().find((step) => !step.result);
  if (pending) {
    const detail = pending.summary?.trim();
    return detail
      ? `Running ${pending.name} — ${detail}`
      : `Running ${pending.name}…`;
  }

  const finished = state.steps.length;
  if (state.thinking.trim().length > 0 && finished === 0) {
    return "Thinking…";
  }
  if (state.thinking.trim().length > 0) {
    return `Thinking — ${finished} tool call${finished === 1 ? "" : "s"} done…`;
  }
  if (state.message.trim().length > 0) {
    return "Writing the answer…";
  }
  return "Contacting the model…";
}
