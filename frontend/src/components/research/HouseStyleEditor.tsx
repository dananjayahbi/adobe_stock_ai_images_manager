"use client";

/**
 * The house standard and house rules editor.
 *
 * Collapsed by default with a state line, because it is a setting the operator
 * changes occasionally — but the badge is what makes it safe to collapse: it
 * always states whether the current text is custom or the shipped default, so a
 * customised standard can never be invisible while it is affecting every run.
 *
 * Persistence is delegated entirely to `useHouseStyle`. This component owns only
 * the disclosure and the per-field dirty/reset wiring.
 */

import { Check, ChevronRight, Loader2, RotateCcw, Save, Scale } from "lucide-react";
import { useEffect, useState } from "react";

import EditableTextBlock from "@/components/research/EditableTextBlock";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/** Kept in step with `backend/services/research/house_style.py`. */
export const MAX_STYLE_CHARS = 8_000;
export const MAX_RULES_CHARS = 8_000;

/** How long the "saved" confirmation stays up. */
const SAVED_TICK_MS = 2_000;

export interface HouseStyleEditorProps {
  styleInstruction: string;
  onStyleChange: (value: string) => void;
  houseRules: string;
  onRulesChange: (value: string) => void;
  /** True when the draft differs from what the server has stored. */
  isDirty: boolean;
  isLoading?: boolean;
  isSaving?: boolean;
  /** Timestamp of the last successful save; drives the confirmation tick. */
  savedAt?: number | null;
  /**
   * False when the field is already the shipped default, so a per-field Reset
   * would be a no-op. Server-derived, so the button cannot offer to restore
   * something that is already restored.
   */
  styleIsCustom?: boolean;
  rulesIsCustom?: boolean;
  onFlush?: () => void;
  /** Restores both fields. */
  onReset?: () => void;
  /** Restores only the style instruction, leaving the rules untouched. */
  onResetStyle?: () => void;
  /** Restores only the house rules, leaving the style untouched. */
  onResetRules?: () => void;
  error?: string | null;
  /** True while a run is streaming — the text is snapshotted per run. */
  disabled?: boolean;
  className?: string;
}

export default function HouseStyleEditor({
  styleInstruction,
  onStyleChange,
  houseRules,
  onRulesChange,
  isDirty,
  isLoading = false,
  isSaving = false,
  savedAt = null,
  styleIsCustom = false,
  rulesIsCustom = false,
  onFlush,
  onReset,
  onResetStyle,
  onResetRules,
  error = null,
  disabled = false,
  className,
}: HouseStyleEditorProps) {
  const [isOpen, setOpen] = useState(false);

  /**
   * Drive the confirmation tick from an effect, not from `savedAt` in the render
   * body: setting state during render re-runs the render, which schedules another
   * timeout, which never settles.
   */
  const [showSaved, setShowSaved] = useState(false);
  useEffect(() => {
    if (!savedAt) return;
    setShowSaved(true);
    const timer = setTimeout(() => setShowSaved(false), SAVED_TICK_MS);
    return () => clearTimeout(timer);
  }, [savedAt]);

  const isBusy = disabled || isLoading;

  return (
    <section
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
        <Scale className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span>House style</span>
        <StatusBadge isDirty={isDirty} isSaving={isSaving} showSaved={showSaved} />
        <ChevronRight
          className={cn("ml-auto h-3.5 w-3.5 transition-transform", isOpen && "rotate-90")}
          aria-hidden
        />
      </button>

      {isOpen ? (
        <div className="space-y-3 border-t border-navy-700/40 px-3 py-3">
          <p className="text-[11px] leading-relaxed text-navy-500">
            Saved on this machine and applied to every run you start, so your
            standard survives a reload — it is not held in the page.
          </p>

          {error ? (
            <p
              role="alert"
              className="rounded-lg border border-red-500/40 bg-red-500/10 px-2.5 py-2 text-[11px] leading-relaxed text-red-200"
            >
              {error}
            </p>
          ) : null}

          <EditableTextBlock
            id="house-style-instruction"
            label="Style instruction"
            hint="Your house standard. The agent follows its look, lens, lighting and framing."
            value={styleInstruction}
            onChange={onStyleChange}
            isDirty={isDirty}
            canReset={styleIsCustom}
            onReset={onResetStyle}
            maxChars={MAX_STYLE_CHARS}
            rows={7}
            disabled={isBusy}
          />

          <EditableTextBlock
            id="house-rules"
            label="House rules"
            hint="The constraints applied on top of your standard — ratio, lens, realism, and Adobe's refusal reasons. These are what keep the output submittable."
            value={houseRules}
            onChange={onRulesChange}
            isDirty={isDirty}
            canReset={rulesIsCustom}
            onReset={onResetRules}
            maxChars={MAX_RULES_CHARS}
            rows={8}
            disabled={isBusy}
          />

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              size="sm"
              variant="secondary"
              icon={<Save className="h-3.5 w-3.5" aria-hidden />}
              disabled={!isDirty || isSaving || isBusy}
              onClick={onFlush}
            >
              {isSaving ? "Saving…" : "Save now"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
              disabled={isSaving || isBusy}
              onClick={onReset}
            >
              Restore defaults
            </Button>
            <span className="ml-auto text-[10px] text-navy-600">
              Changes save automatically as you type.
            </span>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/** The save-state indicator in the header, in a fixed precedence order. */
function StatusBadge({
  isDirty,
  isSaving,
  showSaved,
}: {
  isDirty: boolean;
  isSaving: boolean;
  showSaved: boolean;
}) {
  if (isDirty) {
    return (
      <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[10px] text-accent-200">
        unsaved
      </span>
    );
  }
  if (isSaving) {
    return (
      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-navy-500" aria-hidden />
    );
  }
  if (showSaved) {
    return (
      <span className="flex items-center gap-1 text-[10px] text-emerald-300">
        <Check className="h-3 w-3" aria-hidden />
        saved
      </span>
    );
  }
  return null;
}