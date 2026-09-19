"use client";

import { cn } from "@/lib/cn";

export interface BucketTab {
  id: string;
  label: string;
  count: number;
  tone?: "draft" | "primary" | "success" | "danger" | "neutral";
}

const TONES: Record<NonNullable<BucketTab["tone"]>, { active: string; dot: string }> = {
  draft: { active: "border-navy-500 bg-navy-700/60 text-navy-50", dot: "bg-navy-300" },
  primary: { active: "border-accent-500 bg-accent-500/15 text-accent-200", dot: "bg-accent-400" },
  success: { active: "border-emerald-500/70 bg-emerald-500/15 text-emerald-200", dot: "bg-emerald-400" },
  danger: { active: "border-red-500/70 bg-red-500/15 text-red-200", dot: "bg-red-400" },
  neutral: { active: "border-navy-600 bg-navy-750/70 text-navy-100", dot: "bg-navy-400" },
};

export interface BucketTabsProps {
  tabs: BucketTab[];
  activeId: string;
  onChange: (id: string) => void;
  className?: string;
}

/**
 * Horizontal bucket switcher.
 *
 * Scrolls horizontally on narrow screens rather than wrapping, so the strip
 * never changes height between breakpoints.
 */
export function BucketTabs({ tabs, activeId, onChange, className }: BucketTabsProps) {
  return (
    <div
      role="tablist"
      aria-label="Buckets"
      className={cn(
        "no-scrollbar -mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-1",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeId;
        const tone = TONES[tab.tone ?? "neutral"];
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={cn(
              "inline-flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-xs font-medium",
              "transition-colors duration-150 ease-swift",
              isActive
                ? tone.active
                : "border-navy-700/60 text-navy-300 hover:border-navy-600 hover:text-navy-100"
            )}
          >
            <span
              className={cn(
                "h-1.5 w-1.5 rounded-full",
                isActive ? tone.dot : "bg-navy-600"
              )}
              aria-hidden
            />
            {tab.label}
            <span
              className={cn(
                "rounded-full px-1.5 py-0.5 text-[10px] font-semibold tabular-nums",
                isActive ? "bg-black/25 text-inherit" : "bg-navy-800/80 text-navy-400"
              )}
            >
              {tab.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default BucketTabs;
