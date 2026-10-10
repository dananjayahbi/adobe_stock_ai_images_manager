"use client";

/**
 * The model's chain of thought — collapsed by default, expandable on demand.
 *
 * Auto-opens while streaming (watching the agent think is the point of the live
 * view) and auto-collapses when the turn ends (the operator then wants the
 * answer). An explicit toggle wins until the next run begins.
 */
import { ChevronRight, Brain } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface ThinkingPanelProps {
  /** The model's reasoning, accumulated as it streams. */
  text: string;
  isLive?: boolean;
}

export default function ThinkingPanel({ text, isLive = false }: ThinkingPanelProps) {
  const [isOpen, setOpen] = useState(false);
  // Tracks whether the operator touched the toggle, so the automatic behaviour
  // never fights an explicit choice.
  const touched = useRef(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLive) {
      if (!touched.current) setOpen(false);
      return;
    }
    if (!touched.current) setOpen(true);
  }, [isLive]);

  // Keep the newest reasoning in view as it streams.
  useEffect(() => {
    if (!isOpen || !isLive || !bodyRef.current) return;
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
  }, [text, isOpen, isLive]);

  if (!text.trim()) return null;

  return (
    <div className="overflow-hidden rounded-sm border border-parchment-400 bg-parchment-100">
      <button
        type="button"
        onClick={() => {
          touched.current = true;
          setOpen((open) => !open);
        }}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-parchment-200"
      >
        <Brain
          className={`h-3.5 w-3.5 shrink-0 text-brass-400 ${isLive ? "animate-pulse" : ""}`}
          aria-hidden
        />
        <span className="label-caps">{isLive ? "Thinking…" : "Thinking"}</span>
        <span className="ml-auto text-xs text-ink-400">
          {text.trim().split(/\s+/).length} words
        </span>
        <ChevronRight
          className={`h-3.5 w-3.5 shrink-0 text-ink-400 transition-transform ${
            isOpen ? "rotate-90" : ""
          }`}
          aria-hidden
        />
      </button>
      {isOpen && (
        <div
          ref={bodyRef}
          className="max-h-72 overflow-y-auto border-t border-parchment-400 px-3 py-2.5 text-xs leading-relaxed text-ink-600"
        >
          <p className="whitespace-pre-wrap">{text}</p>
        </div>
      )}
    </div>
  );
}
