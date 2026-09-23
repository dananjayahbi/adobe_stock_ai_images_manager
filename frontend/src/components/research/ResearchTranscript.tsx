"use client";

import { Bot, User } from "lucide-react";

import ThinkingPanel from "@/components/research/ThinkingPanel";
import ToolStepList from "@/components/research/ToolStepList";
import { cn } from "@/lib/cn";
import type { ResearchMessage } from "@/lib/research";
import type { ToolStep } from "@/lib/researchStream";

export interface ResearchTranscriptProps {
  /** The stored conversation, oldest first. */
  messages: ResearchMessage[];
  /**
   * Tool steps for the *last* assistant turn. Earlier turns' steps are not
   * replayed per-message: the events list is flat, and attributing steps to a
   * specific historical turn would be guesswork.
   */
  steps: ToolStep[];
  /** The reasoning for the live/current turn. */
  thinking: string;
  isLive: boolean;
  className?: string;
}

/**
 * The conversation so far.
 *
 * User turns are right-aligned and assistant turns left-aligned — the convention
 * that makes a research thread readable at a glance, and the reason the operator
 * can follow a multi-turn investigation ("continue with this idea") without
 * losing track of which idea was being discussed.
 */
export default function ResearchTranscript({
  messages,
  steps,
  thinking,
  isLive,
  className,
}: ResearchTranscriptProps) {
  if (messages.length === 0 && !isLive) return null;

  const lastAssistantIndex = messages.reduce(
    (found, message, index) => (message.role === "assistant" ? index : found),
    -1
  );

  /**
   * The turn being streamed has no assistant message yet — it is created only
   * when the turn finishes. Rendering live activity *only* inside an assistant
   * message therefore hid the whole first turn: the page showed a spinner while
   * thinking and tool calls were already arriving. When the newest message is
   * the user's, the live activity gets its own block.
   */
  const liveTurnIsPending =
    isLive && messages[messages.length - 1]?.role !== "assistant";

  return (
    <div className={cn("space-y-3", className)}>
      {messages.map((message, index) => {
        const isUser = message.role === "user";
        const isCurrentAssistant = index === lastAssistantIndex;

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
              {/* The live tool activity belongs with the turn that is running. */}
              {!isUser && isCurrentAssistant && steps.length > 0 ? (
                <ToolStepList steps={steps} />
              ) : null}

              {!isUser && isCurrentAssistant && thinking ? (
                <ThinkingPanel text={thinking} isLive={isLive} />
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
      {liveTurnIsPending ? (
        <div className="flex gap-2.5">
          <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-lg bg-accent-500/15 text-accent-300">
            <Bot className="h-3.5 w-3.5" aria-hidden />
          </span>
          <div className="min-w-0 max-w-[85%] space-y-2">
            {steps.length > 0 ? <ToolStepList steps={steps} /> : null}
            {thinking ? <ThinkingPanel text={thinking} isLive={isLive} /> : null}
            {steps.length === 0 && !thinking ? (
              <p className="text-xs text-navy-400">Contacting the model…</p>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
