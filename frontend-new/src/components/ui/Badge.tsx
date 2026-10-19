import type { ReactNode } from "react";

/** Badge tone vocabulary — exported so tone maps (lib/states.ts) stay in sync. */
export type BadgeTone = "neutral" | "success" | "warn" | "danger" | "info";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-parchment-500 text-ink-600 bg-parchment-200",
  success: "border-olive-500 text-olive-400 bg-olive-400/15",
  warn: "border-rust-400 text-rust-400 bg-rust-400/15",
  danger: "border-oxblood-500 text-oxblood-400 bg-oxblood-400/15",
  info: "border-brass-400 text-brass-300 bg-brass-300/20",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}

/** Small stamped label — the reference's postmark motif, toned by state. */
export default function Badge({
  tone = "neutral",
  children,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-sm border px-2 py-0.5 font-stamp text-[10px] uppercase tracking-[0.14em] ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
