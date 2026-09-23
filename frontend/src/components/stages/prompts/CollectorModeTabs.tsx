"use client";

import { Sparkles, Zap } from "lucide-react";

import { cn } from "@/lib/cn";

/** The two Collector modes. */
export type CollectorMode = "advanced" | "quick";

export interface CollectorModeTabsProps {
  mode: CollectorMode;
  onChange: (next: CollectorMode) => void;
  className?: string;
}

const MODES: {
  id: CollectorMode;
  label: string;
  hint: string;
  icon: typeof Sparkles;
}[] = [
  {
    id: "advanced",
    label: "Advanced",
    hint: "Write prompts first, then bind the images they generated.",
    icon: Sparkles,
  },
  {
    id: "quick",
    label: "Quick upload",
    hint: "Upload images only — the original Collector behaviour.",
    icon: Zap,
  },
];

/**
 * Mode switcher for Stage 1.
 *
 * The Collector is the only stage with two working modes. Advanced is the
 * default because the operator's real workflow is prompt-first: the prompt is
 * written before the image exists, so recording it up front is the only moment
 * the link can be captured without guesswork.
 *
 * Implemented as a real tablist so arrow keys and screen readers get the
 * standard tab semantics rather than a pair of toggle buttons.
 */
export function CollectorModeTabs({
  mode,
  onChange,
  className,
}: CollectorModeTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Collector mode"
      className={cn(
        "inline-flex items-center gap-1 rounded-xl border border-navy-700/50 bg-navy-850/60 p-1",
        className
      )}
    >
      {MODES.map((entry) => {
        const isActive = entry.id === mode;
        const Icon = entry.icon;
        return (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            title={entry.hint}
            onClick={() => onChange(entry.id)}
            className={cn(
              "inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs font-medium",
              "transition-colors duration-150 ease-swift",
              isActive
                ? "bg-accent-500/15 text-accent-100 shadow-glow-sm"
                : "text-navy-300 hover:bg-navy-750/60 hover:text-navy-100"
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden />
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

export default CollectorModeTabs;
