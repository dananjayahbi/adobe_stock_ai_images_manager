"use client";

/**
 * One labelled, saved-on-pause textarea in the house-style editor.
 *
 * Extracted because the style instruction and the house rules are the *same
 * interaction* with different content — label, hint, value, dirty flag, reset —
 * and duplicating that markup in `HouseStyleEditor` is how the two fields end up
 * with subtly different behaviour (one losing its save-on-blur, one missing its
 * character counter).
 *
 * Deliberately dumb: no fetching, no timers. Persistence lives in
 * `useHouseStyle`, so this component can be read (and reasoned about) without
 * following an async lifecycle.
 */

import { RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

export interface EditableTextBlockProps {
  id: string;
  label: string;
  hint: string;
  value: string;
  onChange: (value: string) => void;
  /** Shown when the text differs from what is stored. */
  isDirty?: boolean;
  /** Whether a reset would do anything; hides the button when it would not. */
  canReset?: boolean;
  onReset?: () => void;
  /** Advisory limit. Enforced server-side; shown here so the box can warn first. */
  maxChars?: number;
  rows?: number;
  disabled?: boolean;
}

export default function EditableTextBlock({
  id,
  label,
  hint,
  value,
  onChange,
  isDirty = false,
  canReset = false,
  onReset,
  maxChars,
  rows = 5,
  disabled = false,
}: EditableTextBlockProps) {
  const isOverLimit = typeof maxChars === "number" && value.length > maxChars;

  return (
    <div>
      <div className="flex items-center gap-2">
        <label htmlFor={id} className="text-xs font-semibold text-navy-200">
          {label}
        </label>
        {isDirty ? (
          <span className="rounded-full bg-accent-500/15 px-2 py-0.5 text-[10px] text-accent-200">
            unsaved
          </span>
        ) : null}
        {canReset && onReset ? (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-6 px-2 text-[11px]"
            icon={<RotateCcw className="h-3 w-3" aria-hidden />}
            disabled={disabled}
            onClick={onReset}
          >
            Reset
          </Button>
        ) : null}
      </div>
      <p className="mt-0.5 text-[11px] leading-relaxed text-navy-500">{hint}</p>
      <textarea
        id={id}
        value={value}
        disabled={disabled}
        rows={rows}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby={`${id}-hint`}
        aria-invalid={isOverLimit || undefined}
        className={cn(
          "mt-1.5 w-full resize-y rounded-lg border bg-navy-900/50 px-2.5 py-2",
          "text-[11px] leading-relaxed text-navy-200 placeholder:text-navy-600",
          "focus:outline-none disabled:opacity-50",
          isOverLimit
            ? "border-red-500/60 focus:border-red-500"
            : "border-navy-700/50 focus:border-accent-500/50"
        )}
      />
      <p id={`${id}-hint`} className="mt-1 text-[10px] text-navy-600">
        {typeof maxChars === "number"
          ? `${value.length.toLocaleString()} / ${maxChars.toLocaleString()} characters${
              isOverLimit ? " — too long to save" : ""
            }`
          : null}
      </p>
    </div>
  );
}