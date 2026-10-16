"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchRecords, type RecordFilters } from "@/lib/records";
import type { ImageRecord } from "@/lib/types";

/**
 * Offset-paginated records for the gallery's lazy loading.
 *
 * The gallery must survive thousands of images, so it never holds the whole
 * collection: pages are appended on demand (infinite scroll via a sentinel
 * element). Same poll-safe discipline as `useRecords` — a monotonic request
 * id means a filter change during an in-flight request can never be
 * clobbered by the older response landing late.
 */
export function useInfiniteRecords(options: {
  pageSize?: number;
  stageUpdated?: boolean;
} & RecordFilters) {
  const {
    pageSize = 120,
    stageUpdated = false,
    search = "",
    stage = "",
    state = "",
    used = "all",
    groupId,
  } = options;

  const [items, setItems] = useState<ImageRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestId = useRef(0);

  const searchKey = search.trim();
  const stageKey = stage.trim();
  const stateKey = state.trim();
  const groupKey = groupId ?? "";

  /** Load one page; `offset` 0 replaces, later offsets append. */
  const loadPage = useCallback(
    async (offset: number) => {
      const id = ++requestId.current;
      if (offset === 0) setLoading(true);
      else setLoadingMore(true);
      try {
        const data = await fetchRecords({
          limit: pageSize,
          offset,
          search: searchKey || undefined,
          stage: stageKey || undefined,
          state: stateKey || undefined,
          used,
          groupId: groupKey || undefined,
          stageUpdated,
        });
        if (id !== requestId.current) return; // stale — a newer request owns state
        setTotal(data.total);
        setItems((current) =>
          offset === 0 ? data.items : [...current, ...data.items]
        );
        setError(null);
      } catch (err) {
        if (id === requestId.current) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (id === requestId.current) {
          setLoading(false);
          setLoadingMore(false);
        }
      }
    },
    [pageSize, searchKey, stageKey, stateKey, used, groupKey, stageUpdated]
  );

  // A filter change resets to the first page (identity includes the serialised
  // filter keys, never array/object identity).
  useEffect(() => {
    void loadPage(0);
  }, [loadPage]);

  const hasMore = items.length < total;

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore) return;
    void loadPage(items.length);
  }, [loading, loadingMore, hasMore, loadPage, items.length]);

  const reload = useCallback(() => {
    void loadPage(0);
  }, [loadPage]);

  return {
    items,
    total,
    loading,
    loadingMore,
    hasMore,
    error,
    loadMore,
    reload,
  };
}
