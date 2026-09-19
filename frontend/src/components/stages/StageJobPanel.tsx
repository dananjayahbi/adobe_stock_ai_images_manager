"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Loader2,
  MinusCircle,
  X,
} from "lucide-react";

import { formatScore, type StageJob } from "@/lib/stages";

interface StageJobPanelProps {
  job: StageJob;
  onCancel: () => void;
  onDismiss: () => void;
}

const STATUS_ICONS: Record<string, React.ReactNode> = {
  succeeded: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />,
  failed: <AlertTriangle className="h-3.5 w-3.5 text-red-400" />,
  skipped: <MinusCircle className="h-3.5 w-3.5 text-zinc-500" />,
  running: <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-400" />,
  pending: <MinusCircle className="h-3.5 w-3.5 text-zinc-600" />,
};

/**
 * Live progress for a running batch.
 *
 * Long stages (upscale, refine, metadata) take minutes per image, so the
 * per-record log matters as much as the progress bar: it is the only way to see
 * *which* image is slow or failing without waiting for the whole batch.
 */
export default function StageJobPanel({
  job,
  onCancel,
  onDismiss,
}: StageJobPanelProps) {
  const isRunning = job.status === "running";
  const percent = Math.round(job.progress * 100);
  const runningItem = job.items.find(
    (item) => item.record_id === job.current_record_id
  );

  return (
    <section
      aria-label="Batch progress"
      className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4"
    >
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Loader2 className="h-4 w-4 animate-spin text-sky-400" />
          ) : (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          )}
          <h3 className="text-sm font-semibold text-zinc-200">
            {job.kind}
            <span className="ml-2 font-normal text-zinc-500">
              {job.processed}/{job.total} processed
            </span>
          </h3>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500 tabular-nums">
            {job.duration_seconds.toFixed(1)}s
          </span>

          {isRunning ? (
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex items-center gap-1 rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1 text-xs font-medium text-red-200 transition-colors hover:bg-red-500/20"
            >
              <Ban className="h-3.5 w-3.5" />
              Cancel
            </button>
          ) : (
            <button
              type="button"
              onClick={onDismiss}
              aria-label="Dismiss job report"
              className="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </header>

      <div className="mb-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-800">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            job.failed > 0 ? "bg-amber-500" : "bg-sky-500"
          }`}
          style={{ width: `${percent}%` }}
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>

      {job.progress_label && (
        <p className="mb-2 text-xs text-zinc-500">{job.progress_label}</p>
      )}

      <div className="mb-3 flex flex-wrap gap-3 text-xs">
        <span className="text-emerald-400">{job.succeeded} succeeded</span>
        {job.failed > 0 && <span className="text-red-400">{job.failed} failed</span>}
        {job.skipped > 0 && <span className="text-zinc-500">{job.skipped} skipped</span>}
        {job.message && <span className="text-amber-400">{job.message}</span>}
      </div>

      {/* Upscaling takes minutes per image, so the batch bar alone looks stuck.
          This second bar tracks the record in flight. */}
      {isRunning && runningItem && (
        <div className="mb-3 rounded-lg border border-sky-500/25 bg-sky-500/5 px-3 py-2">
          <div className="mb-1.5 flex items-baseline justify-between gap-2 text-xs">
            <span className="min-w-0 truncate text-sky-200">
              {runningItem.filename || runningItem.record_id.slice(0, 8)}
            </span>
            <span className="shrink-0 tabular-nums text-sky-300">
              {runningItem.progress !== null
                ? `${Math.round(runningItem.progress)}%`
                : "working…"}
            </span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-zinc-800">
            <div
              className={`h-full rounded-full transition-[width] duration-300 ${
                runningItem.progress === null
                  ? "w-1/3 animate-pulse bg-sky-500/60"
                  : "bg-sky-400"
              }`}
              style={
                runningItem.progress === null
                  ? undefined
                  : { width: `${runningItem.progress}%` }
              }
              role="progressbar"
              aria-label="Current image progress"
              aria-valuenow={runningItem.progress ?? undefined}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          {runningItem.detail && (
            <p className="mt-1 text-[11px] text-sky-300/70">{runningItem.detail}</p>
          )}
        </div>
      )}

      <ul className="max-h-56 space-y-1 overflow-y-auto pr-1">
        {job.items.map((item) => (
          <li
            key={item.record_id}
            className={`flex items-start gap-2 rounded border px-2 py-1.5 text-xs ${
              item.record_id === job.current_record_id
                ? "border-sky-500/40 bg-sky-500/5"
                : "border-zinc-800/60 bg-zinc-950/40"
            }`}
          >
            {STATUS_ICONS[item.status] ?? STATUS_ICONS.pending}
            <span className="min-w-0 flex-1">
              <span className="block truncate text-zinc-300" title={item.filename}>
                {item.filename || item.record_id.slice(0, 8)}
              </span>
              {item.message && (
                <span className="block text-zinc-500">{item.message}</span>
              )}
              {item.status === "running" && item.detail && (
                <span className="block text-sky-400/80">{item.detail}</span>
              )}
            </span>
            {item.status === "running" && item.progress !== null && (
              <span className="shrink-0 tabular-nums text-sky-300">
                {Math.round(item.progress)}%
              </span>
            )}
            {item.score !== null && (
              <span className="shrink-0 tabular-nums text-zinc-400">
                {formatScore(item.score)}
              </span>
            )}
            {item.duration_seconds !== null && item.status !== "running" && (
              <span className="shrink-0 tabular-nums text-zinc-600">
                {item.duration_seconds.toFixed(1)}s
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
