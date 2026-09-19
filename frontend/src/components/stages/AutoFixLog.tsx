"use client";

/**
 * Decision log for an auto-fix run.
 *
 * The operator asked for "a clear log to see what is happening", and the reason
 * is concrete: the previous single-shot fix reported "fixed 4 issue type(s)"
 * while the score did not move at all, giving no way to tell whether the
 * corrections had failed, been skipped, or been blocked by something outside the
 * engine's control.
 *
 * So this renders *decisions*, not just actions - each pass states what it
 * targeted, what it changed, what the measurements did, and why the loop
 * eventually stopped.
 */

import { AlertTriangle, ArrowRight, CheckCircle2, Info, XCircle } from "lucide-react";

import type { AutoFixLogEntry } from "@/lib/api";
import { cn } from "@/lib/cn";

const LEVEL_STYLES: Record<string, string> = {
  info: "text-navy-300",
  change: "text-accent-200",
  warn: "text-amber-200",
  stop: "text-red-200",
  done: "text-emerald-200",
};

const LEVEL_ICONS: Record<string, typeof Info> = {
  info: Info,
  change: ArrowRight,
  warn: AlertTriangle,
  stop: XCircle,
  done: CheckCircle2,
};

interface AutoFixLogProps {
  entries: AutoFixLogEntry[];
  /** Collapsed by default so the panel does not dominate the modal. */
  defaultOpen?: boolean;
}

export default function AutoFixLog({ entries, defaultOpen = false }: AutoFixLogProps) {
  if (entries.length === 0) return null;

  return (
    <details open={defaultOpen} className="group">
      <summary className="cursor-pointer list-none text-[10px] font-semibold uppercase tracking-wide text-navy-400 hover:text-navy-200">
        Run log ({entries.length})
        <span className="ml-1 font-normal normal-case text-navy-500 group-open:hidden">
          — click to expand
        </span>
      </summary>

      <ol className="mt-2 max-h-72 space-y-1 overflow-y-auto rounded border border-navy-800 bg-navy-950/60 p-2.5">
        {entries.map((entry, index) => {
          const Icon = LEVEL_ICONS[entry.level] ?? Info;
          return (
            <li key={index} className="flex items-start gap-2 text-[11px] leading-snug">
              <Icon
                className={cn(
                  "mt-0.5 h-3 w-3 shrink-0",
                  LEVEL_STYLES[entry.level] ?? "text-navy-400"
                )}
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                {entry.pass > 0 ? (
                  <span className="mr-1 font-mono text-[10px] text-navy-500">
                    p{entry.pass}
                  </span>
                ) : null}
                <span className={LEVEL_STYLES[entry.level] ?? "text-navy-300"}>
                  {entry.message}
                </span>
              </span>
              {entry.score !== null ? (
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-navy-500">
                  {(entry.score * 100).toFixed(1)}%
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>
    </details>
  );
}
