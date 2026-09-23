"use client";

import { ChevronRight, RotateCcw, SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export interface RunSettingsPanelProps {
  /** The editable house standard for this run. */
  styleInstruction: string;
  onStyleChange: (value: string) => void;
  /** The built-in default, so "reset" has somewhere to go. */
  defaultStyle: string;
  /** The fixed rules the operator cannot edit. */
  houseRules: string;
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
 * Per-run settings: the editable style instruction, the prompt count, and the
 * validity toggle.
 *
 * Two design decisions worth stating:
 *
 * * **The style instruction is editable and visible, not hidden behind a modal.**
 *   The operator's reference prompt is the standard the output is judged against,
 *   so they need to see it while reading the result. A collapsed disclosure keeps
 *   it out of the way without hiding it.
 * * **The house rules are shown but NOT editable.** They encode Adobe's refusal
 *   reasons (text, logos, added grain, similar content). A free-text field over
 *   them would let a stylistic tweak silently remove the constraint that keeps
 *   the output submittable.
 */
export default function RunSettingsPanel({
  styleInstruction,
  onStyleChange,
  defaultStyle,
  houseRules,
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
  const isModified = styleInstruction.trim() !== defaultStyle.trim();

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
        {isModified ? (
          <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[10px] text-accent-200">
            style edited
          </span>
        ) : null}
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

          <div>
            <div className="flex items-center gap-2">
              <label
                htmlFor="research-style"
                className="text-xs font-semibold text-navy-200"
              >
                Style instruction
              </label>
              {isModified ? (
                <Button
                  size="sm"
                  variant="ghost"
                  className="ml-auto h-6 px-2 text-[11px]"
                  icon={<RotateCcw className="h-3 w-3" aria-hidden />}
                  disabled={disabled}
                  onClick={() => onStyleChange(defaultStyle)}
                >
                  Reset
                </Button>
              ) : null}
            </div>
            <p className="mt-0.5 text-[11px] leading-relaxed text-navy-500">
              Your house standard. The agent follows its look, lens, lighting and framing.
            </p>
            <textarea
              id="research-style"
              value={styleInstruction}
              disabled={disabled}
              onChange={(event) => onStyleChange(event.target.value)}
              rows={5}
              className="mt-1.5 w-full resize-y rounded-lg border border-navy-700/50 bg-navy-900/50 px-2.5 py-2 text-[11px] leading-relaxed text-navy-200 placeholder:text-navy-600 focus:border-accent-500/50 focus:outline-none disabled:opacity-50"
            />
          </div>

          <details className="rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2">
            <summary className="cursor-pointer text-[11px] font-semibold text-navy-300">
              House rules (fixed)
            </summary>
            <pre className="mt-1.5 whitespace-pre-wrap text-[11px] leading-relaxed text-navy-500">
              {houseRules}
            </pre>
          </details>
        </div>
      ) : null}
    </div>
  );
}
