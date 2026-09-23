"use client";

import { Brain, ChevronRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface ThinkingPanelProps {
  /** The model's reasoning, accumulated as it streams. */
  text: string;
  /** True while the run is live, so the panel stays open and shows a pulse. */
  isLive?: boolean;
  className?: string;
}

/**
 * The model's chain of thought — collapsed by default, expandable on demand.
 *
 * Two behaviours matter here and both were deliberate choices:
 *
 * * **Collapsed by default.** The reasoning is what the operator inspects when
 *   something looks wrong; it is not the answer. Leaving it expanded would push
 *   the actual result off screen on every run.
 * * **Auto-opened while streaming, auto-collapsed when the run ends.** Watching
 *   the agent think is the point of the live view, but once it has finished the
 *   operator wants the answer. The user can override either state at any time —
 *   an explicit toggle wins until the *next* run begins.
 */
export default function ThinkingPanel({
  text,
  isLive = false,
  className,
}: ThinkingPanelProps) {
  const [isOpen, setOpen] = useState(false);
  // Tracks whether the operator has touched the toggle, so the automatic
  // behaviour never fights an explicit choice.
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
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-navy-700/50 bg-navy-850/40",
        className
      )}
    >
      <button
        type="button"
        onClick={() => {
          touched.current = true;
          setOpen((open) => !open);
        }}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-navy-300 transition-colors hover:bg-navy-800/60 hover:text-navy-100"
      >
        <Brain
          className={cn("h-3.5 w-3.5 shrink-0", isLive && "animate-pulse text-accent-300")}
          aria-hidden
        />
        <span>{isLive ? "Thinking…" : "Thinking"}</span>
        <span className="text-navy-500">
          {text.trim().split(/\s+/).length} words
        </span>
        <ChevronRight
          className={cn(
            "ml-auto h-3.5 w-3.5 shrink-0 transition-transform",
            isOpen && "rotate-90"
          )}
          aria-hidden
        />
      </button>

      {isOpen ? (
        <div
          ref={bodyRef}
          className="max-h-72 overflow-y-auto border-t border-navy-700/40 px-3 py-2.5 text-xs leading-relaxed text-navy-400"
        >
          <p className="whitespace-pre-wrap">{text}</p>
        </div>
      ) : null}
    </div>
  );
}
