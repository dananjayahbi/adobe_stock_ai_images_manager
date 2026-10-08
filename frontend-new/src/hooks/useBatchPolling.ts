"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchBatch } from "@/lib/batches";
import type { BatchDetail } from "@/lib/types";

const POLL_MS = 1500;

/**
 * Poll a batch while it runs.
 *
 * Two details that matter:
 * - A monotonic request id (not an in-flight boolean) invalidates responses:
 *   a poll that lands after the batch id changes must not overwrite state.
 * - The interval clears itself when the batch reaches a terminal status, so
 *   the page goes quiet after a run instead of polling forever.
 */
export function useBatchPolling(batchId: string | undefined) {
  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);
  const terminal = useRef(false);

  const refresh = useCallback(async () => {
    if (!batchId) return;
    const id = ++requestId.current;
    try {
      const data = await fetchBatch(batchId);
      if (id !== requestId.current) return; // stale response — a newer id exists
      setBatch(data);
      setError(null);
      if (data.status !== "running") terminal.current = true;
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
  }, [batchId]);

  useEffect(() => {
    if (!batchId) return;
    requestId.current += 1; // invalidate in-flight responses for the old id
    terminal.current = false;
    setBatch(null);
    setError(null);
    void refresh();

    const timer = window.setInterval(() => {
      if (terminal.current) {
        window.clearInterval(timer);
        return;
      }
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [batchId, refresh]);

  return { batch, error, refresh, setBatch };
}
