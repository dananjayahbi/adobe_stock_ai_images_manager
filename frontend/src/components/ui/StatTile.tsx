import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type StatTone = "neutral" | "accent" | "success" | "warning" | "danger";

const TONES: Record<StatTone, { value: string; icon: string }> = {
  neutral: { value: "text-navy-50", icon: "text-navy-300" },
  accent: { value: "text-accent-300", icon: "text-accent-400" },
  success: { value: "text-emerald-300", icon: "text-emerald-400" },
  warning: { value: "text-amber-300", icon: "text-amber-400" },
  danger: { value: "text-red-300", icon: "text-red-400" },
};

export interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Small muted note under the value. */
  hint?: string;
  icon?: ReactNode;
  tone?: StatTone;
  /** Highlights the tile as the currently active metric. */
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

/** A single metric readout. Renders as a button when `onClick` is supplied. */
export function StatTile({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
  active = false,
  onClick,
  className,
}: StatTileProps) {
  const tones = TONES[tone];

  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[11px] font-semibold uppercase tracking-[0.12em] text-navy-400">
          {label}
        </span>
        {icon ? <span className={cn("shrink-0", tones.icon)}>{icon}</span> : null}
      </div>
      <p
        className={cn(
          "mt-2 text-2xl font-semibold tabular-nums tracking-tight",
          tones.value
        )}
      >
        {value}
      </p>
      {hint ? <p className="mt-0.5 truncate text-xs text-navy-400">{hint}</p> : null}
    </>
  );

  const classes = cn(
    "relative overflow-hidden rounded-xl border px-4 py-3.5 text-left transition-colors duration-150 ease-swift",
    active
      ? "border-accent-500/50 bg-accent-500/10"
      : "border-navy-700/50 bg-navy-800/45",
    onClick && !active && "hover:border-navy-600 hover:bg-navy-750/60",
    onClick && "cursor-pointer",
    className
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} className={classes}>
        {body}
      </button>
    );
  }

  return <div className={classes}>{body}</div>;
}

export default StatTile;
