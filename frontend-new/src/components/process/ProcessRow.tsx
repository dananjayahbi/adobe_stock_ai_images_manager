import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import ProgressBar from "@/components/ui/ProgressBar";
import { BATCH_STATUS_LABEL, BATCH_STATUS_TONE } from "./batchStatus";
import { STEP_LABELS } from "@/lib/steps";
import type { Batch } from "@/lib/types";

interface ProcessRowProps {
  batch: Batch;
  /** 1-based position in the run queue — set only for queued batches. */
  position?: number;
  /** Opens the batch detail page (router.push, wired by the board). */
  onOpen: (id: string) => void;
}

/** ISO → display string; falls back to the raw value when unparseable. */
function formatWhen(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

/**
 * One batch in the Processes ledger: name, media type, status, queue
 * position, size, freshness, and the Open shortcut back to its page.
 * Running rows add a live indeterminate progress line — cheap, because the
 * list response already carries `step_progress`.
 */
export default function ProcessRow({ batch, position, onOpen }: ProcessRowProps) {
  const running = batch.status === "running";
  const activeStep = running
    ? batch.steps.find(
        (step) => batch.step_progress?.[step.key]?.status === "running"
      ) ?? null
    : null;
  const progress = activeStep
    ? batch.step_progress?.[activeStep.key] ?? null
    : null;
  const stepLabel = activeStep
    ? STEP_LABELS[activeStep.key] ?? activeStep.key
    : null;

  return (
    <li className="frame-card px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="min-w-0 truncate font-display text-lg text-ink-800">
              {batch.name}
            </h3>
            <Badge tone="info">{batch.media_type}</Badge>
            <Badge tone={BATCH_STATUS_TONE[batch.status]}>
              {BATCH_STATUS_LABEL[batch.status]}
            </Badge>
            {position != null && (
              <span className="inline-flex items-center rounded-sm border border-brass-400 bg-brass-300/20 px-2 py-0.5 font-stamp text-[10px] uppercase tracking-[0.14em] text-brass-300">
                #{position} in queue
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-ink-400">
            {batch.record_count} image{batch.record_count === 1 ? "" : "s"} ·
            updated {formatWhen(batch.updated_at)}
          </p>

          {running && (
            <div className="mt-2 max-w-sm">
              <div className="flex items-center gap-2 font-stamp text-[11px] text-ink-600">
                <span
                  aria-hidden="true"
                  className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-brass-300"
                />
                <span className="truncate">
                  {progress?.message ??
                    (stepLabel ? `Running ${stepLabel}…` : "Running…")}
                </span>
              </div>
              <div className="mt-1.5">
                <ProgressBar value={null} tone="brass" />
              </div>
            </div>
          )}
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => onOpen(batch.id)}
          title="Open this batch"
        >
          Open →
        </Button>
      </div>
    </li>
  );
}
