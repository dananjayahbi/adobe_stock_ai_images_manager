"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRecords, type RecordPage } from "@/lib/records";

/**
 * Fetch records with the standard poll-safe loader pattern: a monotonic
 * request id means a filter change during an in-flight request can never be
 * clobbered by the older response landing late.
 */
export function useRecords(options: {
  limit?: number;
  search?: string;
  stageUpdated?: boolean;
  pollMs?: number;
}) {
  const { limit = 12, search = "", stageUpdated = false, pollMs = 0 } = options;
  const [page, setPage] = useState<RecordPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  // Serialize the query into primitives — never an array/object identity,
  // which would retrigger the effect on every render.
  const searchKey = search.trim();

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const data = await fetchRecords({
        limit,
        search: searchKey || undefined,
        stageUpdated,
      });
      if (id === requestId.current) {
        setPage(data);
        setError(null);
      }
    } catch (err) {
      if (id === requestId.current) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [limit, searchKey, stageUpdated]);

  useEffect(() => {
    void load();
    if (pollMs <= 0) return;
    const timer = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(timer);
  }, [load, pollMs]);

  return { page, loading, error, reload: load };
}
