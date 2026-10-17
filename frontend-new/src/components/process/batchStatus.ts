import type { BadgeTone } from "@/components/ui/Badge";
import type { Batch, BatchStatus } from "@/lib/types";

/**
 * Batch status → badge tone, shared by the batch header and the Processes
 * list so the two views can never drift. `queued` is brass like `running`:
 * both are *in flight*, and the queue-position chip carries the difference.
 */
export const BATCH_STATUS_TONE: Record<BatchStatus, BadgeTone> = {
  draft: "neutral",
  queued: "info",
  running: "info",
  completed: "success",
  failed: "danger",
  cancelled: "warn",
};

/** In flight: waiting in the run queue or actively processing. */
export function isBatchActive(status: BatchStatus): boolean {
  return status === "queued" || status === "running";
}

/** Terminal states — the run has ended (well or badly). */
export function isBatchFinished(status: BatchStatus): boolean {
  return status === "completed" || status === "failed" || status === "cancelled";
}

/**
 * Queue position per batch id (1-based), from the queued batches ordered by
 * `queued_at` ascending — the server's serial-queue contract. Batches with a
 * null `queued_at` sort last among queued.
 */
export function queuePositions(batches: Batch[]): Map<string, number> {
  const queued = batches
    .filter((batch) => batch.status === "queued")
    .sort((a, b) => (a.queued_at ?? "~").localeCompare(b.queued_at ?? "~"));
  const positions = new Map<string, number>();
  queued.forEach((batch, index) => positions.set(batch.id, index + 1));
  return positions;
}
