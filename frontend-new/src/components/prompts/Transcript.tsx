"use client";

/**
 * The conversation so far: stored messages plus the live turn's activity.
 *
 * User turns are right-aligned, assistant turns left — the convention that
 * makes a multi-turn investigation readable at a glance.
 *
 * **Every** assistant turn carries its own reasoning and tool steps: turns are
 * counted in the order the assistant replies appear (matching the backend's
 * `run_finished` boundaries), so `turns[n]` attaches to the n-th assistant
 * bubble. A turn that ended with activity but no message is rendered explicitly
 * below the list rather than dropped — its work was live when the operator was
 * reading it, and losing it at the moment the run ends is how a stopped run
 * became uninspectable.
 */
import { Bot, User } from "lucide-react";

import type { ResearchMessage } from "@/lib/research";
import {
  orphanedTurn,
  type ResearchStreamState,
  type TurnActivity,
} from "@/lib/researchStream";
import ThinkingPanel from "./ThinkingPanel";
import ToolSteps from "./ToolSteps";

interface TranscriptProps {
  /** The stored conversation, oldest first. */
  messages: ResearchMessage[];
  /** The whole accumulated state (live buffers + per-turn history). */
  state: ResearchStreamState;
  isLive: boolean;
}

export default function Transcript({ messages, state, isLive }: TranscriptProps) {
  if (messages.length === 0 && !isLive) return null;

  const { steps, thinking, turns } = state;
  const assistantMessages = messages.filter((entry) => entry.role !== "user").length;
  const orphan = orphanedTurn(state, assistantMessages);

  let assistantSeen = -1;

  return (
    <div className="space-y-3">
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
            className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : ""}`}
          >
            <span
              className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-sm border ${
                isUser
                  ? "border-parchment-500 bg-parchment-200 text-ink-600"
                  : "border-brass-400/50 bg-brass-300/10 text-brass-300"
              }`}
            >
              {isUser ? (
                <User className="h-3.5 w-3.5" aria-hidden />
              ) : (
                <Bot className="h-3.5 w-3.5" aria-hidden />
              )}
            </span>

            <div className={`min-w-0 max-w-[85%] space-y-2 ${isUser ? "text-right" : ""}`}>
              {/* The completed turn's own work, replayed from stored events. */}
              {activity && activity.steps.length > 0 && (
                <ToolSteps steps={activity.steps} />
              )}
              {activity && activity.thinking && (
                <ThinkingPanel text={activity.thinking} />
              )}

              <div
                className={`rounded-sm border px-3 py-2 text-left text-sm leading-relaxed ${
                  isUser
                    ? "border-parchment-500 bg-parchment-200 text-ink-800"
                    : "border-parchment-400 bg-parchment-100 text-ink-600"
                }`}
              >
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              </div>
            </div>
          </div>
        );
      })}

      {/* The in-progress turn, before its assistant message exists. */}
      {isLive && (
        <div className="flex gap-2.5">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-sm border border-brass-400/50 bg-brass-300/10 text-brass-300">
            <Bot className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 max-w-[85%] space-y-2">
            {steps.length > 0 && <ToolSteps steps={steps} />}
            {thinking && <ThinkingPanel text={thinking} isLive />}
            {state.message && (
              <div className="rounded-sm border border-parchment-400 bg-parchment-100 px-3 py-2 text-sm leading-relaxed text-ink-600">
                <p className="whitespace-pre-wrap break-words">{state.message}</p>
              </div>
            )}
            {steps.length === 0 && !thinking && !state.message && (
              <p className="text-xs text-ink-400">Contacting the model…</p>
            )}
          </div>
        </div>
      )}

      {/*
        The final turn when it produced no assistant message — a stopped run, a
        truncated reply, a spent tool budget. Shown rather than dropped: this
        reasoning was streaming while the operator watched.
      */}
      {orphan && (
        <div className="flex gap-2.5">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-sm border border-parchment-500 bg-parchment-200 text-ink-400">
            <Bot className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 max-w-[85%] space-y-2">
            {orphan.steps.length > 0 && <ToolSteps steps={orphan.steps} />}
            {orphan.thinking && <ThinkingPanel text={orphan.thinking} />}
            <p className="text-xs text-ink-400">
              This turn ended without a written answer.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
