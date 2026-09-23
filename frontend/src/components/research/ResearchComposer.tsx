"use client";

import { CornerDownLeft, Loader2, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export interface ResearchComposerProps {
  /** Called with the trimmed message. */
  onSubmit: (message: string) => void;
  /** Abort the in-flight turn. */
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  /** Copy for the placeholder, which changes with the mode. */
  placeholder?: string;
  /** Quick prompts shown above the box when the conversation is empty. */
  suggestions?: string[];
  /**
   * What the agent is doing right now, streamed from the run. Shown instead of a
   * bare spinner: "working" tells the operator nothing, and a research turn can
   * legitimately run for a minute.
   */
  activity?: string;
  className?: string;
}

/**
 * The chat composer.
 *
 * Enter sends, Shift+Enter adds a line — the convention every chat interface
 * uses, and the reason a plain `<textarea>` is used rather than a one-line input:
 * a niche description is often a paragraph.
 *
 * The draft is **local state**. Binding the textarea to the parent's message list
 * would make typing impossible while a request is in flight, because the parent
 * re-renders on every streamed token.
 */
export default function ResearchComposer({
  onSubmit,
  onStop,
  isStreaming,
  disabled = false,
  placeholder = "Describe the niche or idea…",
  suggestions = [],
  activity,
  className,
}: ResearchComposerProps) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to a ceiling, then scroll. A fixed-height box hides
  // the line being typed on a long niche description.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [draft]);

  const canSend = draft.trim().length > 0 && !isStreaming && !disabled;

  function submit() {
    if (!canSend) return;
    onSubmit(draft.trim());
    setDraft("");
  }

  return (
    <div className={cn("space-y-2", className)}>
      {suggestions.length > 0 && !isStreaming ? (
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={disabled}
              onClick={() => setDraft(suggestion)}
              className="rounded-full border border-navy-700/60 bg-navy-800/50 px-2.5 py-1 text-[11px] text-navy-300 transition-colors hover:border-accent-500/40 hover:text-navy-100 disabled:opacity-40"
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}

      <div className="rounded-xl border border-navy-700/50 bg-navy-850/50 p-2">
        <textarea
          ref={textareaRef}
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          rows={2}
          disabled={disabled}
          placeholder={placeholder}
          aria-label="Research message"
          className="max-h-[200px] w-full resize-none bg-transparent px-2 py-1.5 text-sm text-navy-100 placeholder:text-navy-500 focus:outline-none disabled:opacity-50"
        />

        <div className="flex items-center gap-2 px-1 pt-1">
          <p className="text-[11px] text-navy-500">
            Enter to send · Shift+Enter for a new line
          </p>

          <div className="ml-auto">
            {isStreaming ? (
              <Button
                size="sm"
                variant="secondary"
                icon={<Square className="h-3 w-3" aria-hidden />}
                onClick={onStop}
              >
                Stop
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                disabled={!canSend}
                icon={<CornerDownLeft className="h-3.5 w-3.5" aria-hidden />}
                onClick={submit}
              >
                Send
              </Button>
            )}
          </div>
        </div>
      </div>

      {isStreaming ? (
        <p className="flex items-center gap-1.5 text-[11px] text-accent-300">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          <span className="truncate">
            {activity ?? "The agent is working — you can stop it at any time."}
          </span>
        </p>
      ) : null}
    </div>
  );
}
