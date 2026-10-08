import type { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  body?: string;
  action?: ReactNode;
  /** Decorative glyph shown in a dashed circle, e.g. "№1" or an icon. */
  glyph?: ReactNode;
}

/** Empty-library state — a blank plate in the reference's ticket style. */
export default function EmptyState({
  title,
  body,
  action,
  glyph,
}: EmptyStateProps) {
  return (
    <div className="frame-card flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full border-2 border-dashed border-parchment-500 font-script text-2xl text-parchment-600">
        {glyph ?? "✦"}
      </div>
      <h3 className="font-display text-xl text-ink-800">{title}</h3>
      {body && <p className="mt-2 max-w-md text-ink-400">{body}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
