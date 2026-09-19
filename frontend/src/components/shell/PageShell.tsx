import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export interface PageShellProps {
  children: ReactNode;
  /** Wider gutter on very large displays; the shell itself is always fluid. */
  className?: string;
}

/**
 * The one page shell every route uses.
 *
 * Intentionally **full width** — no `max-w-*` — with only a responsive gutter
 * so content spans the whole viewport at any size.
 */
export function PageShell({ children, className }: PageShellProps) {
  return (
    <main
      className={cn(
        "mx-auto w-full space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 xl:px-10",
        className
      )}
    >
      {children}
    </main>
  );
}

export default PageShell;
