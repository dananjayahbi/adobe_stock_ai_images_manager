"use client";

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface SettingsFieldProps {
  id: string;
  label: string;
  /** Explanatory line under the label; use it to state the format we expect. */
  hint?: ReactNode;
  /** Rendered to the right of the label, e.g. a "current" badge. */
  badge?: ReactNode;
  /** Inline validation or error text; replaces the hint when present. */
  error?: string | null;
  children: ReactNode;
  className?: string;
}

const CONTROL_CLASSES =
  "w-full rounded-lg border bg-navy-900/70 px-3 py-2 text-sm text-navy-50 " +
  "placeholder:text-navy-500 transition-colors duration-150 " +
  "focus:outline-none focus:ring-2 focus:ring-accent-500/40 disabled:opacity-50";

/** Shared input styling, so every control in the dialog matches. */
export function controlClass(hasError: boolean): string {
  return cn(
    CONTROL_CLASSES,
    hasError
      ? "border-red-500/60 focus:border-red-400"
      : "border-navy-700/60 focus:border-accent-500/60"
  );
}

/**
 * One labelled setting row.
 *
 * Extracted so the four LLM fields share identical label, hint, and error
 * layout; a fifth field later needs no new markup.
 */
export function SettingsField({
  id,
  label,
  hint,
  badge,
  error,
  children,
  className,
}: SettingsFieldProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-xs font-medium text-navy-200">
          {label}
        </label>
        {badge}
      </div>
      {children}
      {error ? (
        <p role="alert" className="text-[11px] leading-relaxed text-red-300">
          {error}
        </p>
      ) : hint ? (
        <p className="text-[11px] leading-relaxed text-navy-400">{hint}</p>
      ) : null}
    </div>
  );
}

export default SettingsField;
