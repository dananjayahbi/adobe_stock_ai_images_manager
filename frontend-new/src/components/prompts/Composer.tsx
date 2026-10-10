"use client";

/**
 * The chat composer.
 *
 * Enter sends, Shift+Enter adds a line — the convention every chat interface
 * uses, and the reason this is a `<textarea>` rather than a one-line input: a
 * niche description is often a paragraph.
 *
 * The draft is **local state**. Binding it to the page's message list would make
 * typing impossible while a request is in flight, because the page re-renders on
 * every streamed token.
 */
import { CornerDownLeft, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import Button from "@/components/ui/Button";
import { hintClass, inputClass } from "./fieldStyles";

interface ComposerProps {
  /** Called with the trimmed message. */
  onSubmit: (message: string) => void;
  /** Abort the in-flight turn. */
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  placeholder?: string;
  /**
   * What the agent is doing right now, streamed from the run. Shown instead of
   * a bare spinner: a research turn can legitimately run for a minute.
   */
  activity?: string;
}

export default function Composer({
  onSubmit,
  onStop,
  isStreaming,
  disabled = false,
  placeholder = "Describe the niche, idea, or prompts you need…",
  activity,
}: ComposerProps) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to a ceiling, then scroll. A fixed-height box
  // hides the line being typed on a long description.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  }, [draft]);

  const canSend = draft.trim().length > 0 && !isStreaming && !disabled;

  const submit = () => {
    if (!canSend) return;
    onSubmit(draft.trim());
    setDraft("");
  };

  return (
    <div className="space-y-2">
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
        disabled={disabled || isStreaming}
        placeholder={placeholder}
        aria-label="Research message"
        className={`${inputClass} max-h-[200px] resize-none leading-relaxed`}
      />

      <div className="flex items-center gap-3">
        <p className={hintClass}>Enter to send · Shift+Enter for a new line</p>
        <div className="ml-auto">
          {isStreaming ? (
            <Button size="sm" variant="secondary" type="button" onClick={onStop}>
              <Square className="h-3 w-3" aria-hidden />
              Stop
            </Button>
          ) : (
            <Button
              size="sm"
              type="button"
              disabled={!canSend}
              onClick={submit}
            >
              <CornerDownLeft className="h-3.5 w-3.5" aria-hidden />
              Send
            </Button>
          )}
        </div>
      </div>

      {isStreaming && activity && (
        <p className="flex items-center gap-2 font-stamp text-[11px] uppercase tracking-[0.14em] text-brass-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-brass-400" aria-hidden />
          {activity}
        </p>
      )}
    </div>
  );
}
