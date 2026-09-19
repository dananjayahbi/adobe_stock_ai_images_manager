import { cn } from "@/lib/cn";

export interface ProgressBarProps {
  /** 0-100. */
  value: number;
  tone?: "accent" | "success" | "danger" | "warning";
  className?: string;
  /** Accessible label; omit to render a purely decorative bar. */
  label?: string;
}

const FILLS: Record<NonNullable<ProgressBarProps["tone"]>, string> = {
  accent: "bg-accent-sheen",
  success: "bg-emerald-500",
  danger: "bg-red-500",
  warning: "bg-amber-500",
};

/** Thin rounded progress track used by jobs, scores, and uploads. */
export function ProgressBar({ value, tone = "accent", className, label }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-navy-750", className)}
      role={label ? "progressbar" : undefined}
      aria-label={label}
      aria-valuenow={label ? Math.round(pct) : undefined}
      aria-valuemin={label ? 0 : undefined}
      aria-valuemax={label ? 100 : undefined}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-500 ease-swift", FILLS[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export default ProgressBar;
