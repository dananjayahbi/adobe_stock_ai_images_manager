import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface PageHeaderProps {
  /** Stage number, e.g. `2`. Omit for non-stage pages. */
  step?: number;
  title: string;
  tagline?: string;
  icon?: ReactNode;
  /** Right-aligned slot for the page's primary actions. */
  actions?: ReactNode;
  /** Rendered directly under the title row — e.g. a bucket tab strip. */
  children?: ReactNode;
  className?: string;
}

/**
 * Page masthead.
 *
 * Deliberately full-bleed (no `max-w-*`): the layout is fluid at every
 * breakpoint, which is what the redesign calls for.
 */
export function PageHeader({
  step,
  title,
  tagline,
  icon,
  actions,
  children,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("border-b border-navy-700/40 pb-5", className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4">
        <div className="flex min-w-0 items-start gap-3.5">
          {icon ? (
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-accent-500/25 bg-accent-500/10 text-accent-300">
              {icon}
            </span>
          ) : null}
          <div className="min-w-0">
            {step !== undefined ? (
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-400">
                Stage {step}
              </p>
            ) : null}
            <h1 className="mt-0.5 truncate text-2xl font-semibold tracking-tight text-white sm:text-[28px]">
              {title}
            </h1>
            {tagline ? (
              <p className="mt-1 max-w-3xl text-sm leading-relaxed text-navy-300">
                {tagline}
              </p>
            ) : null}
          </div>
        </div>
        {actions ? (
          <div className="flex flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {children ? <div className="mt-5">{children}</div> : null}
    </header>
  );
}

export default PageHeader;
