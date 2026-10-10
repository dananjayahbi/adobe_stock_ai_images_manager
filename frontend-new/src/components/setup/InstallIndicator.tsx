import { INSTALL_STATE_LABELS, jobProgress } from "@/lib/setup";
import type { SetupStatus } from "@/lib/setup";

interface InstallIndicatorProps {
  /** Shared hook state — rendered as-is, never snapshotted locally. */
  status: SetupStatus | null;
  onOpen: () => void;
}

/**
 * Persistent "an install is running" control, rendered by the page (outside
 * the modal) and visible only while `status.running`. This is what makes the
 * download popup background-capable from the operator's point of view:
 * closing the modal leaves this behind, and clicking it reopens the dialog
 * onto the same live progress — the state lives in the page-level hook, not
 * in either component.
 */
export default function InstallIndicator({ status, onOpen }: InstallIndicatorProps) {
  if (!status?.running) return null;

  const { state } = status.install;
  // Same helper the modal reads, so the pill and the dialog can never show two
  // different percentages for one multi-group job.
  const { percent } = jobProgress(status);
  const label = INSTALL_STATE_LABELS[state];

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={`${label} — ${Math.round(percent)}%. Reopen install progress.`}
      className="fixed right-4 top-20 z-50 flex items-center gap-3 rounded-sm border border-brass-400/70 bg-parchment-50 px-4 py-2 shadow-raised transition-transform hover:-translate-y-0.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400"
    >
      <span
        aria-hidden="true"
        className="h-3 w-3 animate-spin rounded-full border-2 border-brass-400 border-t-transparent"
      />
      <span className="font-stamp text-xs uppercase tracking-[0.14em] text-ink-800">
        {label}
      </span>
      <span className="font-stamp text-xs text-oxblood-400">
        {Math.round(percent)}%
      </span>
      <span
        aria-hidden="true"
        className="h-1.5 w-20 overflow-hidden rounded-full border border-parchment-400 bg-parchment-200"
      >
        <span
          className="block h-full bg-brass-400 transition-[width] duration-500"
          style={{ width: `${Math.max(0, Math.min(100, percent))}%` }}
        />
      </span>
    </button>
  );
}
