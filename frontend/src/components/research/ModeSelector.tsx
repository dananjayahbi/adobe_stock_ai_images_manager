"use client";

import { Search, Sparkles, Lightbulb, Layers } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ResearchMode, ResearchModeSpec } from "@/lib/research";

/** Icons per mode. Presentation only, so it lives here rather than in the API. */
const MODE_ICONS: Record<ResearchMode, LucideIcon> = {
  static: Sparkles,
  batch: Layers,
  research: Search,
  ideas: Lightbulb,
};

export interface ModeSelectorProps {
  modes: ResearchModeSpec[];
  value: ResearchMode;
  onChange: (mode: ResearchMode) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * The four research objectives as a card row.
 *
 * Rendered from the **backend's** mode list rather than a hard-coded array, so a
 * mode cannot be offered in the UI that the API would reject. A card rather than
 * a tab strip because each mode needs its own explanation — "research" and
 * "find ideas" differ in what they produce, and a one-word tab would not say so.
 */
export default function ModeSelector({
  modes,
  value,
  onChange,
  disabled = false,
  className,
}: ModeSelectorProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Research mode"
      className={cn("grid gap-2 sm:grid-cols-2 xl:grid-cols-4", className)}
    >
      {modes.map((mode) => {
        const Icon = MODE_ICONS[mode.id] ?? Sparkles;
        const isActive = mode.id === value;
        return (
          <button
            key={mode.id}
            type="button"
            role="radio"
            aria-checked={isActive}
            disabled={disabled}
            onClick={() => onChange(mode.id)}
            className={cn(
              "flex flex-col items-start gap-1 rounded-xl border px-3 py-2.5 text-left transition-colors duration-150",
              isActive
                ? "border-accent-500/50 bg-accent-500/10"
                : "border-navy-700/50 bg-navy-850/40 hover:border-navy-600 hover:bg-navy-800/60",
              disabled && "cursor-not-allowed opacity-50"
            )}
          >
            <span className="flex items-center gap-1.5">
              <Icon
                className={cn("h-3.5 w-3.5", isActive ? "text-accent-300" : "text-navy-400")}
                aria-hidden
              />
              <span
                className={cn(
                  "text-xs font-semibold",
                  isActive ? "text-accent-200" : "text-navy-200"
                )}
              >
                {mode.label}
              </span>
              {mode.researches ? (
                <span className="rounded-full bg-navy-750/80 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-navy-400">
                  web
                </span>
              ) : null}
            </span>
            <span className="text-[11px] leading-snug text-navy-400">{mode.tagline}</span>
          </button>
        );
      })}
    </div>
  );
}

export interface ModeDescriptionProps {
  mode: ResearchModeSpec | undefined;
  className?: string;
}

/** The full explanation of the active mode. */
export function ModeDescription({ mode, className }: ModeDescriptionProps) {
  if (!mode) return null;
  return (
    <p className={cn("text-xs leading-relaxed text-navy-400", className)}>
      {mode.description}
    </p>
  );
}
