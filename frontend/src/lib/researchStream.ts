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
  ResearchContextReport,
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

/**
 * One assistant turn's own activity, kept so it survives the turn ending.
 *
 * The event stream is a single flat list across the whole conversation, so
 * attributing a tool step to a turn means segmenting it. The backend marks the
 * boundary: every turn is followed by its own `run_finished`, so the next
 * `run_started` (or the end of the list) closes the previous segment.
 *
 * Without this, only the *last* turn's thinking and steps were rendered, so
 * reopening a finished conversation showed an answer with no trace of how it was
 * reached — the operator could not inspect earlier work at all.
 */
export interface TurnActivity {
  /** 0-based index of the assistant turn this activity belongs to. */
  turn: number;
  thinking: string;
  message: string;
  steps: ToolStep[];
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
  /** The latest context-window measurement, or null before the first one. */
  context: ResearchContextReport | null;
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
  /**
   * Per-turn activity, so a completed conversation stays fully inspectable.
   *
   * `thinking`/`steps` above remain the *current* turn's, which is what the live
   * view renders; this list is the durable history of every turn's work.
   */
  turns: TurnActivity[];
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
    context: null,
    followUpActions: [],
    notices: [],
    error: "",
    isStreaming: false,
    finished: false,
    mode: "",
    tools: [],
    maxToolCalls: 0,
    turns: [],
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

/**
 * Close the current turn's activity into the durable list.
 *
 * Called on every turn boundary. A turn that produced nothing (no reasoning and
 * no tool calls) is not recorded, so the list stays a list of *work*, not of
 * request round-trips.
 *
 * The live buffers are returned **cleared**, which makes this idempotent. That
 * matters because a failed turn emits *both* `error` and `run_finished` — the
 * backend's error path yields the error and then the terminal event — so calling
 * this twice must not append the same activity as two turns.
 */
function closeTurn(state: ResearchStreamState): Pick<
  ResearchStreamState,
  "turns" | "thinking" | "message" | "steps"
> {
  if (!state.thinking && state.steps.length === 0) {
    return { turns: state.turns, thinking: "", message: "", steps: [] };
  }
  return {
    turns: [
      ...state.turns,
      {
        turn: state.turns.length,
        thinking: state.thinking,
        message: state.message,
        steps: state.steps,
      },
    ],
    thinking: "",
    message: "",
    steps: [],
  };
}

/**
 * The activity the *last* archived turn holds, or ``null``.
 *
 * Exported for a caller that wants to restate what the agent was doing (a
 * "stopped" banner, for example) without reading `turns.at(-1)` itself.
 */
export function lastArchived(state: ResearchStreamState): TurnActivity | null {
  return state.turns.at(-1) ?? null;
}

export function reduceEvent(
  state: ResearchStreamState,
  event: ResearchEvent
): ResearchStreamState {
  switch (event.type) {
    case "run_started":
      // A new turn begins. Any activity still in the live buffers belongs to the
      // *previous* turn, so it is archived before the buffers are cleared —
      // otherwise a multi-turn conversation lost every earlier turn's reasoning.
      return {
        ...state,
        mode: event.mode ?? state.mode,
        tools: event.tools ?? state.tools,
        maxToolCalls: event.max_tool_calls ?? state.maxToolCalls,
        ...closeTurn(state),
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

    case "context": {
      // Latest wins: each report measures the conversation as it stands, so the
      // final one describes the completed run. `type` is the discriminant, so it
      // is dropped rather than carried into the report's own shape.
      const { type: _type, ...report } = event;
      return { ...state, context: report };
    }

    case "notice":
      // Deduplicated: a repeated notice would stack the same banner.
      return state.notices.includes(event.text)
        ? state
        : { ...state, notices: [...state.notices, event.text] };

    case "error": {
      // Spread `closed`, not `state`: `closeTurn` returns the buffers *cleared*,
      // and spreading `state` would keep the thinking and steps live — so the
      // `run_finished` that follows would archive the same activity a second time
      // and the transcript would show one turn as two.
      const closed = closeTurn(state);
      return {
        ...state,
        ...closed,
        error: event.text,
        finished: true,
        isStreaming: false,
      };
    }

    case "run_finished": {
      // The final turn's activity is closed into `turns`. It is deliberately NOT
      // promoted back into the live buffers: a promoted buffer would be archived
      // again by the next turn's `run_started`, duplicating the turn.
      //
      // Visibility for a turn that ended without an assistant message is handled
      // by `orphanedTurn`, which the transcript renders explicitly — measured
      // live, a run whose last turn stopped without writing an answer lost the
      // reasoning the operator was reading the moment it finished.
      const closed = closeTurn(state);
      return {
        ...state,
        ...closed,
        answer: event.answer?.trim() || state.message.trim(),
        isStreaming: false,
        finished: true,
      };
    }

    default:
      return state;
  }
}

/**
 * The trailing turn's activity, when no assistant message exists for it.
 *
 * The transcript renders one assistant bubble per stored message and attaches
 * `turns[n]` to the n-th one. A turn that ended without producing a message — a
 * stopped run, a truncated reply, a spent tool budget — has activity but no
 * message, so its thinking and steps have nothing to attach to and vanish. This
 * returns that orphaned activity so the transcript can render it explicitly.
 *
 * Only the *last* turn can be orphaned: every earlier turn is followed by the
 * next turn's assistant message, which the operator can see.
 */
export function orphanedTurn(
  state: ResearchStreamState,
  assistantMessages: number
): TurnActivity | null {
  if (state.isStreaming) return null;
  const index = state.turns.length - 1;
  if (index < 0 || index < assistantMessages) return null;
  const turn = state.turns[index];
  if (!turn || (!turn.thinking && turn.steps.length === 0)) return null;
  return turn;
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
