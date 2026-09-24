"use client";

import { Bot, User } from "lucide-react";

import ThinkingPanel from "@/components/research/ThinkingPanel";
import ToolStepList from "@/components/research/ToolStepList";
import { cn } from "@/lib/cn";
import type { ResearchMessage } from "@/lib/research";
import {
  orphanedTurn,
  type ResearchStreamState,
  type ToolStep,
  type TurnActivity,
} from "@/lib/researchStream";

export interface ResearchTranscriptProps {
  /** The stored conversation, oldest first. */
  messages: ResearchMessage[];
  /** Tool steps for the turn currently streaming. */
  steps: ToolStep[];
  /** The reasoning for the turn currently streaming. */
  thinking: string;
  /**
   * Activity for *completed* turns, oldest first.
   *
   * The event stream is one flat list, so attributing a tool step to a specific
   * historical turn needs a boundary. The backend provides one â€” every turn ends
   * with its own `run_finished` â€” and the reducer segments on it, so each
   * assistant message can be shown with the work that produced it.
   */
  turns: TurnActivity[];
  /**
   * The whole accumulated state, so a turn that ended without producing an
   * assistant message can still be rendered (see :func:`orphanedTurn`).
   */
  state: ResearchStreamState;
  isLive: boolean;
  className?: string;
}

/**
 * The conversation so far.
 *
 * User turns are right-aligned and assistant turns left-aligned â€” the convention
 * that makes a research thread readable at a glance, and the reason the operator
 * can follow a multi-turn investigation ("continue with this idea") without
 * losing track of which idea was being discussed.
 *
 * **Every** assistant turn carries its own reasoning and tool steps. An earlier
 * version attached them only to the last turn, so reopening a finished
 * conversation showed answers with no trace of how they were reached and the
 * operator could not inspect the research at all.
 */
export default function ResearchTranscript({
  messages,
  steps,
  thinking,
  turns,
  state,
  isLive,
  className,
}: ResearchTranscriptProps) {
  if (messages.length === 0 && !isLive) return null;

  /**
   * Map each assistant message to the activity of the turn that produced it.
   *
   * Turns are counted in the order the assistant replies appear, which matches
   * the order the backend emitted them: a `run_finished` closes a turn, and the
   * next assistant message is the next turn.
   */
  let assistantSeen = -1;
  const assistantMessages = messages.filter((entry) => entry.role !== "user").length;
  /**
   * A turn that ended without producing a message has nowhere to attach its
   * activity, so it is rendered on its own below the transcript. Without this a
   * stopped or truncated run lost the reasoning the operator was reading the
   * moment it finished â€” the reported "after it stopped, the thinking parts are
   * gone".
   */
  const orphan = orphanedTurn(state, assistantMessages);

  return (
    <div className={cn("space-y-3", className)}>
      {messages.map((message, index) => {
        const isUser = message.role === "user";
        let activity: TurnActivity | undefined;
        if (!isUser) {
          assistantSeen += 1;
          activity = turns[assistantSeen];
        }

        return (
          <div
            key={`${index}-${message.created_at ?? ""}`}
            className={cn("flex gap-2.5", isUser && "flex-row-reverse")}
          >
            <span
              className={cn(
                "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg",
                isUser
                  ? "bg-navy-700/60 text-navy-200"
                  : "bg-accent-500/15 text-accent-300"
              )}
            >
              {isUser ? (
                <User className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Bot className="h-3.5 w-3.5" aria-hidden />
              )}
            </span>

            <div className={cn("min-w-0 max-w-[85%] space-y-2", isUser && "items-end")}>
              {/* The completed turn's own work, replayed from the stored events. */}
              {activity && activity.steps.length > 0 ? (
                <ToolStepList steps={activity.steps} />
              ) : null}
              {activity && activity.thinking ? (
                <ThinkingPanel text={activity.thinking} isLive={false} />
              ) : null}

              <div
                className={cn(
                  "rounded-xl border px-3 py-2 text-sm leading-relaxed",
                  isUser
                    ? "border-navy-700/50 bg-navy-750/50 text-navy-100"
                    : "border-navy-700/40 bg-navy-850/50 text-navy-200"
                )}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
              </div>
            </div>
          </div>
        );
      })}

      {/* The in-progress turn, before its assistant message exists. */}
      {isLive ? (
        <div className="flex gap-2.5">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-accent-500/15 text-accent-300">
            <Bot className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 max-w-[85%] space-y-2">
            {steps.length > 0 ? <ToolStepList steps={steps} /> : null}
            {thinking ? <ThinkingPanel text={thinking} isLive /> : null}
            {steps.length === 0 && !thinking ? (
              <p className="text-xs text-navy-400">Contacting the modelâ€¦</p>
            ) : null}
          </div>
        </div>
      ) : null}
      {/*
        The final turn when it produced no assistant message — a stopped run, a
        truncated reply, or a tool budget spent mid-research. Its reasoning and
        steps are real work the operator was reading while it streamed, so they are
        shown rather than dropped at the moment the run ends.
      */}
      {orphan ? (
        <div className="flex gap-2.5">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-navy-700/40 text-navy-300">
            <Bot className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 max-w-[85%] space-y-2">
            {orphan.steps.length > 0 ? <ToolStepList steps={orphan.steps} /> : null}
            {orphan.thinking ? (
              <ThinkingPanel text={orphan.thinking} isLive={false} />
            ) : null}
            <p className="text-xs text-navy-400">
              This turn ended without a written answer.
            </p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
