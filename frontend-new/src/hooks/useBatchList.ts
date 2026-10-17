"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { listBatches } from "@/lib/batches";
import { isBatchActive } from "@/components/process/batchStatus";
import type { Batch } from "@/lib/types";

/** Cadence while something is queued/running — the operator is watching. */
const ACTIVE_POLL_MS = 1500;
/** Cadence at rest — keeps drafts/finished fresh without hammering. */
const IDLE_POLL_MS = 15000;
/** The backend caps `limit` at 200; 50 covers a working queue. */
const LIST_LIMIT = 50;

/**
 * Poll the batch list with dual cadence (the useSetupStatus pattern): 1.5s
 * while any batch is queued or running, 15s otherwise. The interval is
 * re-armed whenever `active` flips, so a Run from a batch page speeds the
 * next tick up and a finished queue speeds it back down.
 *
 * A monotonic request id guards every response — a poll that lands after a
 * newer one (or after unmount) must not overwrite fresher state.
 */
export function useBatchList() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const active = batches.some((batch) => isBatchActive(batch.status));

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const data = await listBatches(LIST_LIMIT);
      if (id !== requestId.current) return; // stale response — a newer id exists
      setBatches(data.items);
      setTotal(data.total);
      setError(null);
    } catch (err) {
      if (id === requestId.current) {
        // Keep the last good list on a transient poll failure; only the
        // first load ever shows the error in place of rows.
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(
      () => void refresh(),
      active ? ACTIVE_POLL_MS : IDLE_POLL_MS
    );
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  return { batches, total, loading, error, refresh };
}
