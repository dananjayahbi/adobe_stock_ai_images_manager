"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRecords, type RecordFilters, type RecordPage } from "@/lib/records";

/**
 * Fetch records with the standard poll-safe loader pattern: a monotonic
 * request id means a filter change during an in-flight request can never be
 * clobbered by the older response landing late.
 */
export function useRecords(options: {
  limit?: number;
  stageUpdated?: boolean;
  pollMs?: number;
} & RecordFilters) {
  const {
    limit = 12,
    stageUpdated = false,
    pollMs = 0,
    search = "",
    stage = "",
    used = "all",
    groupId,
  } = options;
  const [page, setPage] = useState<RecordPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  // Serialize the query into primitives — never an array/object identity,
  // which would retrigger the effect on every render.
  const searchKey = search.trim();
  const stageKey = stage.trim();
  const groupKey = groupId ?? "";

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      const data = await fetchRecords({
        limit,
        search: searchKey || undefined,
        stage: stageKey || undefined,
        used,
        groupId: groupKey || undefined,
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
  }, [limit, searchKey, stageKey, used, groupKey, stageUpdated]);

  useEffect(() => {
    void load();
    if (pollMs <= 0) return;
    const timer = window.setInterval(() => void load(), pollMs);
    return () => window.clearInterval(timer);
  }, [load, pollMs]);

  return { page, loading, error, reload: load };
}
