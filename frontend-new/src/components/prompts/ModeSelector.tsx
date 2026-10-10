"use client";

import { Lightbulb, Search, Sparkles } from "lucide-react";

import type { ResearchMode, ResearchModeSpec } from "@/lib/research";

/** Icon per mode. Presentation only, so it lives here rather than in the API. */
const MODE_ICONS: Record<string, typeof Sparkles> = {
  generate: Sparkles,
  research: Search,
  ideas: Lightbulb,
};

interface ModeSelectorProps {
  modes: ResearchModeSpec[];
  value: ResearchMode;
  onChange: (mode: ResearchMode) => void;
  disabled?: boolean;
}

/**
 * The three research objectives as a card row, rendered from the **backend's**
 * mode list so a mode can never be offered that the API would reject. Cards
 * rather than tabs because each mode needs its own explanation — "research"
 * and "find ideas" differ in what they produce.
 */
export default function ModeSelector({
  modes,
  value,
  onChange,
  disabled = false,
}: ModeSelectorProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Research mode"
      className="grid gap-3 sm:grid-cols-3"
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
            className={`frame-card px-4 py-3 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 ${
              isActive
                ? "-translate-y-0.5 border-oxblood-500 ring-1 ring-oxblood-500"
                : "hover:-translate-y-0.5"
            } ${disabled ? "cursor-not-allowed opacity-60" : ""}`}
          >
            <span className="flex items-center gap-2">
              <Icon
                className={`h-4 w-4 ${isActive ? "text-oxblood-400" : "text-brass-400"}`}
                aria-hidden
              />
              <span className="font-display text-base text-ink-800">
                {mode.label}
              </span>
              {mode.researches && (
                <span className="ml-auto rounded-sm border border-parchment-500 px-1.5 py-0.5 font-stamp text-[9px] uppercase tracking-[0.14em] text-ink-400">
                  web
                </span>
              )}
            </span>
            <span className="mt-1 block text-xs leading-snug text-ink-400">
              {mode.tagline}
            </span>
          </button>
        );
      })}
    </div>
  );
}
