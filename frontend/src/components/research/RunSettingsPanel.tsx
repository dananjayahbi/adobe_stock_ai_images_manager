"use client";

import { ChevronRight, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

export interface RunSettingsPanelProps {
  /** Number of prompts wanted; only meaningful in the prompt-producing modes. */
  count: number;
  onCountChange: (value: number) => void;
  maxPrompts: number;
  /** Whether this mode uses the prompt count at all. */
  showCount: boolean;
  /** Whether this mode can run the validity check. */
  showValidity: boolean;
  validityCheck: boolean;
  onValidityChange: (value: boolean) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * Per-run settings: the prompt count and the validity toggle.
 *
 * **The house style is deliberately not here.** It used to be — an editable style
 * textarea plus a read-only rules block — which meant two boxes describing the
 * same thing on one page, and the style box was the one whose text was never
 * saved anywhere. The style and the rules now live in
 * {@link HouseStyleEditor}, persisted server-side; this panel holds only the
 * choices that are genuinely scoped to a single run.
 */
export default function RunSettingsPanel({
  count,
  onCountChange,
  maxPrompts,
  showCount,
  showValidity,
  validityCheck,
  onValidityChange,
  disabled = false,
  className,
}: RunSettingsPanelProps) {
  const [isOpen, setOpen] = useState(false);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-xl border border-navy-700/50 bg-navy-850/40",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((open) => !open)}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-medium text-navy-300 transition-colors hover:bg-navy-800/60 hover:text-navy-100"
      >
        <SlidersHorizontal className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>Run settings</span>
        <ChevronRight
          className={cn("ml-auto h-3.5 w-3.5 transition-transform", isOpen && "rotate-90")}
          aria-hidden
        />
      </button>

      {isOpen ? (
        <div className="space-y-3 border-t border-navy-700/40 px-3 py-3">
          {showCount ? (
            <div>
              <label
                htmlFor="research-count"
                className="text-xs font-semibold text-navy-200"
              >
                Prompts to generate
              </label>
              <p className="mt-0.5 text-[11px] leading-relaxed text-navy-500">
                Each prompt describes a different image. Overlaps are flagged before you save.
              </p>
              <div className="mt-1.5 flex items-center gap-2">
                <input
                  id="research-count"
                  type="range"
                  min={1}
                  max={Math.min(20, maxPrompts)}
                  value={count}
                  disabled={disabled}
                  onChange={(event) => onCountChange(Number(event.target.value))}
                  className="h-1.5 flex-1 cursor-pointer accent-accent-500 disabled:opacity-40"
                />
                <span className="w-8 shrink-0 text-right text-sm font-semibold tabular-nums text-accent-300">
                  {count}
                </span>
              </div>
            </div>
          ) : null}

          {showValidity ? (
            <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2">
              <input
                type="checkbox"
                checked={validityCheck}
                disabled={disabled}
                onChange={(event) => onValidityChange(event.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-pointer accent-accent-500"
              />
              <span>
                <span className="block text-xs font-semibold text-navy-200">
                  Validity check
                </span>
                <span className="mt-0.5 block text-[11px] leading-relaxed text-navy-500">
                  The agent researches the idea first, scores it, and waits for your
                  decision before writing any prompts.
                </span>
              </span>
            </label>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
