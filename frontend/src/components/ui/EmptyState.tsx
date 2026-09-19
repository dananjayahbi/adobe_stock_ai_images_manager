import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  /** Call to action, e.g. a `<Button />`. */
  action?: ReactNode;
  /** Use the dashed placeholder treatment (for grid areas). */
  dashed?: boolean;
  className?: string;
}

/** Placeholder for an empty grid, list, or panel. */
export function EmptyState({
  title,
  description,
  icon,
  action,
  dashed = true,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl px-6 py-14 text-center",
        dashed
          ? "border border-dashed border-navy-700/60 bg-navy-850/30"
          : "border border-navy-700/40 bg-navy-800/30",
        className
      )}
    >
      {icon ? (
        <span className="grid h-11 w-11 place-items-center rounded-xl border border-navy-700/60 bg-navy-800/70 text-navy-400">
          {icon}
        </span>
      ) : null}
      <div>
        <p className="text-sm font-medium text-navy-100">{title}</p>
        {description ? (
          <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-navy-400">
            {description}
          </p>
        ) : null}
      </div>
      {action}
    </div>
  );
}

export default EmptyState;
