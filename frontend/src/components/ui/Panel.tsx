import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface PanelProps {
  children: ReactNode;
  className?: string;
  /** Renders a lighter, flatter surface for nested content. */
  inset?: boolean;
  /** Adds the diagonal sheen from the reference compositions. */
  sheen?: boolean;
}

/**
 * The base surface.
 *
 * Panels are translucent navy with a hairline border and an inner top
 * highlight, so stacked panels read as one continuous surface rather than
 * a set of boxes.
 */
export function Panel({ children, className, inset = false, sheen = false }: PanelProps) {
  return (
    <div
      className={cn(
        "relative rounded-xl border",
        inset
          ? "border-navy-700/40 bg-navy-850/40"
          : "border-navy-700/50 bg-navy-800/45 shadow-panel",
        sheen && "before:pointer-events-none before:absolute before:inset-0 before:rounded-xl before:bg-panel-sheen before:content-['']",
        className
      )}
    >
      {children}
    </div>
  );
}

export interface PanelHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Consistent panel heading: icon, title, optional description, right actions. */
export function PanelHeader({
  title,
  description,
  icon,
  actions,
  className,
}: PanelHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 border-b border-navy-700/40 px-4 py-3",
        className
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        {icon ? (
          <span className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-accent-500/25 bg-accent-500/10 text-accent-300">
            {icon}
          </span>
        ) : null}
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-navy-50">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-xs leading-relaxed text-navy-300">{description}</p>
          ) : null}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export default Panel;
