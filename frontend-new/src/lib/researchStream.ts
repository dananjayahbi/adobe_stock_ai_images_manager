/**
 * The stream reducer: folds research events into the state the UI renders.
 *
 * Kept as a pure function, separate from the hook that feeds it, because the
 * live view, a replayed stored run and a unit test must all go through the
 * *same* code — a reload replays `run.events` through this reducer so a
 * restored view cannot disagree with the live one.
 *
 * The state is *accumulated*, never recomputed: events arrive incrementally and
 * the answer is the concatenation of many `message` chunks.
 */
import type {
  FollowUpAction,
  ResearchEvent,
  ResearchPrompt,
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
 * The event stream is one flat list across the conversation, so attributing a
 * step to a turn means segmenting it. The backend marks the boundary — every
 * turn ends with its own `run_finished` — so the next `run_started` closes the
 * previous segment. Without this, only the *last* turn's thinking and steps
 * rendered, and reopening a finished run showed an answer with no trace of how
 * it was reached.
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
  /** The final answer, once the terminal event arrives. */
  answer: string;
  steps: ToolStep[];
  prompts: ResearchPrompt[];
  /** The model's own one-line statement of what it produced. */
  promptSummary: string;
  validity: ResearchValidity | null;
  /**
   * Every scorecard the current turn produced — an `ideas` turn assesses each
   * idea separately and each assessment renders its own card. `validity` above
   * keeps its single-slot meaning (the latest assessment) for older readers;
   * old runs replaying through this reducer fill the list the same way.
   */
  validities: ResearchValidity[];
  /** The turn `validities` was built in — a later turn replaces the set. */
  validityTurn: number | null;
  followUpActions: FollowUpAction[];
  notices: string[];
  error: string;
  /** True between the request starting and a terminal event arriving. */
  isStreaming: boolean;
  finished: boolean;
  /** The mode the run actually used. */
  mode: string;
  /**
   * Per-turn activity, so a completed conversation stays fully inspectable.
   * `thinking`/`steps` above remain the *current* turn's, which is what the
   * live view renders; this list is the durable history of every turn's work.
   */
  turns: TurnActivity[];
}

export function initialState(): ResearchStreamState {
  return {
    thinking: "",
    message: "",
    answer: "",
    steps: [],
    prompts: [],
    promptSummary: "",
    validity: null,
    validities: [],
    validityTurn: null,
    followUpActions: [],
    notices: [],
    error: "",
    isStreaming: false,
    finished: false,
    mode: "",
    turns: [],
  };
}

/**
 * Close the current turn's activity into the durable list.
 *
 * Called on every turn boundary. A turn that produced nothing is not recorded,
 * so the list stays a list of *work*, not of request round-trips. The live
 * buffers are returned **cleared**, which makes this idempotent — a failed turn
 * emits *both* `error` and `run_finished`, so calling it twice must not append
 * the same activity as two turns.
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

export function reduceEvent(
  state: ResearchStreamState,
  event: ResearchEvent
): ResearchStreamState {
  switch (event.type) {
    case "run_started":
      // A new turn begins: whatever is still live belongs to the *previous*
      // turn, so it is archived before the buffers clear — otherwise a
      // multi-turn conversation lost every earlier turn's reasoning.
      return { ...state, mode: event.mode ?? state.mode, ...closeTurn(state) };

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
      // Attach to the *last step with this name that has no result yet*, not
      // simply the last step: a model may call two tools in one turn and the
      // results arrive in order, so matching by name keeps each summary with
      // its own call.
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

    case "prompts":
      return {
        ...state,
        prompts: event.prompts ?? [],
        promptSummary: event.summary?.trim() ?? "",
      };

    case "validity": {
      // Scorecards accumulate *within the turn that produced them*: an `ideas`
      // turn calls `assess_validity` once per idea and each call must render
      // its own card. A later turn replaces the set, so a research follow-up
      // still shows exactly the one assessment it produced — the old
      // single-slot behaviour for every non-ideas mode.
      const turn = state.turns.length;
      const entry = event.validity ?? null;
      const continues = entry !== null && state.validityTurn === turn;
      return {
        ...state,
        validity: entry,
        validities: entry
          ? continues
            ? [...state.validities, entry]
            : [entry]
          : state.validities,
        validityTurn: entry ? turn : state.validityTurn,
        // New actions replace old ones; absent keeps the previous set so a
        // re-describe without buttons does not silently drop the gate.
        followUpActions: event.follow_up_actions ?? state.followUpActions,
      };
    }

    case "notice":
      // Deduplicated: a repeated notice would stack the same banner.
      return state.notices.includes(event.text)
        ? state
        : { ...state, notices: [...state.notices, event.text] };

    case "error": {
      // Spread `closed`, not `state`: `closeTurn` returns the buffers *cleared*,
      // and spreading `state` would keep the thinking live — so the
      // `run_finished` that follows would archive the same activity twice.
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
      // The final turn's activity is closed into `turns` and deliberately NOT
      // promoted back into the live buffers: a promoted buffer would be archived
      // again by the next turn's `run_started`, duplicating the turn. Visibility
      // for a turn that ended without an assistant message is `orphanedTurn`.
      const closed = closeTurn(state);
      return {
        ...state,
        ...closed,
        answer: event.answer?.trim() || state.message.trim(),
        isStreaming: false,
        finished: true,
      };
    }

    // `sources`/`context` events are accepted by `parseEvent` but not rendered
    // on this page — dropped here rather than accumulated into unused state.
    default:
      return state;
  }
}

/**
 * The trailing turn's activity, when no assistant message exists for it.
 *
 * The transcript renders one bubble per stored message and attaches `turns[n]`
 * to the n-th assistant bubble. A turn that ended without producing a message —
 * a stopped run, a truncated reply, a spent tool budget — has activity but no
 * message, so its work would vanish the moment the run ended. Only the *last*
 * turn can be orphaned: every earlier turn is followed by an assistant message
 * the operator can see.
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
 * A bare spinner tells the operator nothing during a turn that can legitimately
 * run for a minute — this reports the observable facts the stream already
 * carries, so "working" never stands alone.
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
