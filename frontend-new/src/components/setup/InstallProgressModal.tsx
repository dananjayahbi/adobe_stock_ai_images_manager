"use client";

import { useEffect, useRef, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import ProgressBar from "@/components/ui/ProgressBar";
import { formatMbRange } from "@/lib/format";
import { INSTALL_STATE_LABELS, jobProgress } from "@/lib/setup";
import type { SetupStatus } from "@/lib/setup";

interface InstallProgressModalProps {
  open: boolean;
  /** Hides the modal only — never cancels the server-side install. */
  onClose: () => void;
  status: SetupStatus | null;
  /** Action-layer error (e.g. a 409) shown while the dialog is open. */
  error?: string | null;
  /** Live install state; the parent keeps polling while this is closed. */
  onCancel: () => void;
  cancelBusy: boolean;
}

/** How close to the bottom (px) still counts as "pinned" for auto-scroll. */
const PIN_THRESHOLD_PX = 48;

const FINISHED_TONE: Record<string, string> = {
  done: "text-olive-400",
  failed: "text-oxblood-400",
  cancelled: "text-rust-400",
};

/**
 * Determinate download popup for the server-side install.
 *
 * Closing (button, backdrop, Esc) only flips `open` — the job runs on the
 * server and the page-level hook keeps polling, so the progress shown here
 * is always a fresh read of shared state, never a local snapshot that dies
 * with the dialog.
 *
 * Log auto-scroll: the pane follows new lines only while it is *pinned* to
 * the bottom. Scrolling up unpins (and a programmatic jump to the bottom
 * re-pins), so a user reading an old error is never yanked back down. The
 * pin is component state — the hint line under the pane reads the same
 * value, so it can never disagree with what the pane actually does.
 */
export default function InstallProgressModal({
  open,
  onClose,
  status,
  error,
  onCancel,
  cancelBusy,
}: InstallProgressModalProps) {
  const logRef = useRef<HTMLDivElement | null>(null);
  const [pinned, setPinned] = useState(true);

  const install = status?.install ?? null;
  const logLines = install?.log ?? [];
  const logKey = logLines.length > 0 ? logLines[logLines.length - 1] : "";

  // Follow the tail only while pinned. Runs after render, so the freshly
  // appended line is already in the DOM when scrollTop is measured. The
  // scroll handler's own setPinned re-enters here, which is what re-pins
  // when the user scrolls back to the bottom themselves.
  useEffect(() => {
    const el = logRef.current;
    if (!el || !pinned || !open) return;
    el.scrollTop = el.scrollHeight;
  }, [logKey, open, pinned]);

  const handleLogScroll = () => {
    const el = logRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    // Crossing under the threshold re-pins: the user returns to live.
    setPinned(distance <= PIN_THRESHOLD_PX);
  };

  const state = install?.state ?? "idle";
  const running = status?.running ?? false;
  const finished = state === "done" || state === "failed" || state === "cancelled";
  const bytesLine =
    install && install.bytes_total > 0
      ? formatMbRange(install.bytes_done, install.bytes_total)
      : "—";

  // Job-wide progress (see `jobProgress`): the engine installs one group at a
  // time and its own percent restarts for each, so this folds the finished
  // groups back in to give one bar for the whole job — the same number the
  // floating indicator shows, because both come from this shared helper.
  const job = jobProgress(status);

  return (
    <Modal open={open} onClose={onClose} width="max-w-2xl" labelledBy="install-modal-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps text-oxblood-400">Server setup</p>
        <div className="mt-0.5 flex items-baseline justify-between gap-3">
          <h2 id="install-modal-title" className="font-display text-xl text-ink-800">
            Install dependencies
          </h2>
          <span className="font-stamp text-xs uppercase tracking-[0.14em] text-ink-400">
            {INSTALL_STATE_LABELS[state]}
          </span>
        </div>
      </div>

      <div className="space-y-4 px-6 py-5">
        {!status ? (
          <p className="text-sm text-ink-400">Fetching install status…</p>
        ) : (
          <>
            <div>
              <div className="mb-1 flex items-baseline justify-between">
                <span className="label-caps">
                  {install?.phase || "Waiting to start"}
                </span>
                <span className="font-stamp text-xs text-ink-600">
                  {job.percent}%
                </span>
              </div>
              <ProgressBar
                value={job.percent}
                tone={state === "failed" ? "oxblood" : "brass"}
              />
              <div className="mt-1 flex items-baseline justify-between gap-3">
                <span className="font-stamp text-[11px] text-ink-400">
                  {bytesLine}
                </span>
                {install?.current_file && (
                  <span
                    className="truncate font-mono text-[11px] text-ink-400"
                    title={install.current_file}
                  >
                    {install.current_file}
                  </span>
                )}
              </div>
              {job.total > 1 && job.current && (
                <p className="mt-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
                  {finished
                    ? `${job.total} packages in this job`
                    : `Package ${Math.min(job.done + 1, job.total)} of ${job.total} · ${job.current.label}`}
                </p>
              )}
            </div>

            {error && (
              <p
                className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
                role="alert"
              >
                {error}
              </p>
            )}

            {finished && (
              <p
                className={`rounded-sm border border-parchment-400/70 bg-parchment-200/60 px-3 py-2 font-stamp text-xs uppercase tracking-[0.14em] ${FINISHED_TONE[state] ?? "text-ink-600"}`}
                role={state === "failed" ? "alert" : "status"}
              >
                {state === "done" && "Install finished"}
                {state === "cancelled" && "Install cancelled"}
                {state === "failed" && "Install failed"}
              </p>
            )}

            {state === "failed" && install?.error && (
              <p
                className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
                role="alert"
              >
                {install.error}
              </p>
            )}

            <div>
              <p className="label-caps mb-1">Log</p>
              <div
                ref={logRef}
                onScroll={handleLogScroll}
                className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-sm border border-parchment-400/70 bg-ink-900/40 px-3 py-2 font-mono text-xs leading-relaxed text-ink-600"
                aria-label="Install log"
              >
                {logLines.length === 0 ? (
                  <span className="text-ink-400">No output yet.</span>
                ) : (
                  logLines.map((line, index) => (
                    <div key={index}>{line === "" ? "\u00A0" : line}</div>
                  ))
                )}
              </div>
              <p className="mt-1 font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
                {pinned ? "Following new lines" : "Scroll to bottom to resume following"}
              </p>
            </div>
          </>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-dashed border-parchment-400 px-6 py-4">
        <p className="text-[11px] text-ink-400">
          Closing this dialog does not stop the install — progress keeps
          running in the background.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          {running && (
            <Button
              variant="danger"
              size="sm"
              type="button"
              disabled={cancelBusy}
              onClick={onCancel}
            >
              Cancel install
            </Button>
          )}
          <Button variant="secondary" size="sm" type="button" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  );
}
