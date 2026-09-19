import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type BannerTone = "error" | "success" | "info" | "warning";

const TONES: Record<BannerTone, { shell: string; icon: ReactNode }> = {
  error: {
    shell: "border-red-500/40 bg-red-500/10 text-red-100",
    icon: <AlertTriangle className="h-4 w-4 text-red-300" aria-hidden />,
  },
  warning: {
    shell: "border-amber-500/40 bg-amber-500/10 text-amber-100",
    icon: <AlertTriangle className="h-4 w-4 text-amber-300" aria-hidden />,
  },
  success: {
    shell: "border-emerald-500/40 bg-emerald-500/10 text-emerald-100",
    icon: <CheckCircle2 className="h-4 w-4 text-emerald-300" aria-hidden />,
  },
  info: {
    shell: "border-accent-500/35 bg-accent-500/10 text-navy-100",
    icon: <Info className="h-4 w-4 text-accent-300" aria-hidden />,
  },
};

export interface BannerProps {
  tone?: BannerTone;
  children: ReactNode;
  /** Extra content aligned to the right, e.g. an action button. */
  actions?: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

/** Inline status message. One implementation for the whole app. */
export function Banner({
  tone = "info",
  children,
  actions,
  onDismiss,
  className,
}: BannerProps) {
  const style = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex flex-wrap items-start justify-between gap-3 rounded-xl border px-4 py-3 text-sm",
        style.shell,
        className
      )}
    >
      <div className="flex min-w-0 items-start gap-2.5">
        <span className="mt-0.5 shrink-0">{style.icon}</span>
        <div className="min-w-0 leading-relaxed">{children}</div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {actions}
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="rounded-md p-1 opacity-70 transition-opacity hover:opacity-100"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        ) : null}
      </div>
    </div>
  );
}

export default Banner;
