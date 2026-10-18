import type { ReactNode } from "react";

interface ProcessSectionProps {
  /** Stable id fragment for the aria-labelledby wiring. */
  id: string;
  label: string;
  /** Right-aligned muted descriptor, e.g. "running or queued". */
  caption: string;
  /** Shown instead of rows when the section has no batches. */
  emptyText: string;
  children: ReactNode;
}

/** One titled group in the Processes page (Active / Drafts / Processed / Finished). */
export default function ProcessSection({
  id,
  label,
  caption,
  emptyText,
  children,
}: ProcessSectionProps) {
  const empty = children == null || (Array.isArray(children) && children.length === 0);

  return (
    <section aria-labelledby={`${id}-heading`}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p id={`${id}-heading`} className="label-caps">
          {label}
        </p>
        <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
          {caption}
        </span>
      </div>
      {/* The section stays mounted even when empty so the layout never jumps
          as batches move through the queue — a muted line fills the slot. */}
      {empty ? (
        <p className="frame-card px-5 py-4 text-sm text-ink-400">{emptyText}</p>
      ) : (
        <ul className="space-y-3">{children}</ul>
      )}
    </section>
  );
}
