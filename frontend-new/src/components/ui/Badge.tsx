import type { ReactNode } from "react";

type Tone = "neutral" | "success" | "warn" | "danger" | "info";

const TONES: Record<Tone, string> = {
  neutral: "border-parchment-500 text-ink-600 bg-parchment-200",
  success: "border-olive-500 text-olive-600 bg-olive-400/15",
  warn: "border-rust-400 text-rust-600 bg-rust-400/15",
  danger: "border-oxblood-500 text-oxblood-600 bg-oxblood-400/15",
  info: "border-brass-400 text-brass-700 bg-brass-300/20",
};

interface BadgeProps {
  tone?: Tone;
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
