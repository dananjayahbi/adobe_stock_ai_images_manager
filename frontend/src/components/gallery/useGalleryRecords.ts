"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  deleteRecord,
  deleteRecords,
  downloadRecordsZip,
  fetchRecords,
  setRecordUsed,
  setRecordsUsed,
  type BulkActionResult,
  type ImageRecord,
  type UsageFilter,
} from "@/lib/api";
import {
  PUBLISHED_STAGES,
  type GalleryScope,
} from "@/lib/galleryFilters";

const POLL_INTERVAL_MS = 5000;
const PAGE_LIMIT = 500;

export interface GalleryCounts {
  all: number;
  used: number;
  unused: number;
}

/** Re-exported so existing importers keep working while the type lives with
 *  the rest of the filter vocabulary. */
export type StatusScope = GalleryScope;

/**
 * Owns all gallery data: fetching, polling, and the mutating operations
 * (usage toggles, deletes, ZIP download).
 */
export function useGalleryRecords() {
  const [records, setRecords] = useState<ImageRecord[]>([]);
  const [counts, setCounts] = useState<GalleryCounts>({ all: 0, used: 0, unused: 0 });
  const [usageFilter, setUsageFilter] = useState<UsageFilter>("unused");
  // Default to the published gallery: it is the system's endpoint, and an
  // operator opening it wants finished assets rather than work in progress.
  const [statusScope, setStatusScope] = useState<StatusScope>("published");
  const [search, setSearch] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Monotonic request id: only the newest response is ever applied. Using a
  // generation counter instead of an "in flight" guard means a filter change
  // is never silently dropped while a poll is still running.
  const requestId = useRef(0);
  const filterRef = useRef<UsageFilter>(usageFilter);
  filterRef.current = usageFilter;
  const scopeRef = useRef<StatusScope>(statusScope);
  scopeRef.current = statusScope;
  const searchRef = useRef(search);
  searchRef.current = search;

  const load = useCallback(async (showSpinner = false) => {
    const id = ++requestId.current;
    if (showSpinner) setIsLoading(true);

    // Scope by *stage*, not by the legacy status column. `status` is the QC
    // verdict, so `status=READY` also matched records that were approved but not
    // yet published - which is not what "browse published" means.
    const scopeStages =
      scopeRef.current === "published" ? PUBLISHED_STAGES : undefined;
    const term = searchRef.current.trim() || undefined;

    try {
      // Fetch the active filter plus the aggregate counts in parallel. The
      // counts deliberately ignore the search term: they describe the scope, and
      // a count that changed as you typed would make the chips look unstable.
      const [filtered, all, used] = await Promise.all([
        fetchRecords({
          stages: scopeStages,
          used: filterRef.current,
          search: term,
          limit: PAGE_LIMIT,
        }),
        fetchRecords({ stages: scopeStages, used: "all", limit: 1 }),
        fetchRecords({ stages: scopeStages, used: "used", limit: 1 }),
      ]);

      if (id !== requestId.current) return; // superseded by a newer request

      setRecords(filtered.items);
      setCounts({
        all: all.total,
        used: used.total,
        unused: Math.max(all.total - used.total, 0),
      });
      setError(null);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : "Failed to load the gallery.");
    } finally {
      if (id === requestId.current && showSpinner) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load, usageFilter, statusScope, search]);

  useEffect(() => {
    const interval = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const runMutation = useCallback(
    async (operation: () => Promise<void>, failureMessage: string) => {
      setIsBusy(true);
      try {
        await operation();
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : failureMessage);
      } finally {
        setIsBusy(false);
      }
    },
    [load]
  );

  const toggleUsed = useCallback(
    (record: ImageRecord) =>
      runMutation(async () => {
        await setRecordUsed(record.id, !record.is_used);
        setNotice(
          !record.is_used
            ? "Marked as used."
            : "Marked as unused."
        );
      }, "Failed to update usage."),
    [runMutation]
  );

  const markUsed = useCallback(
    (ids: string[], isUsed: boolean) =>
      runMutation(async () => {
        const result: BulkActionResult = await setRecordsUsed(ids, isUsed);
        setNotice(
          `Updated ${result.updated} image(s)${result.missing.length ? ` · ${result.missing.length} not found` : ""}.`
        );
      }, "Failed to update usage."),
    [runMutation]
  );

  const removeOne = useCallback(
    (record: ImageRecord) =>
      runMutation(async () => {
        await deleteRecord(record.id);
        setNotice("Image deleted.");
      }, "Failed to delete the image."),
    [runMutation]
  );

  const removeMany = useCallback(
    (ids: string[]) =>
      runMutation(async () => {
        const result = await deleteRecords(ids);
        setNotice(
          `Deleted ${result.deleted} image(s)${result.missing.length ? ` · ${result.missing.length} not found` : ""}.`
        );
      }, "Failed to delete the selected images."),
    [runMutation]
  );

  const downloadZip = useCallback(
    (ids: string[]) =>
      runMutation(async () => {
        await downloadRecordsZip(ids);
      }, "Failed to build the ZIP archive."),
    [runMutation]
  );

  const clearNotice = useCallback(() => setNotice(null), []);

  /** Clear the search and both filters - what "show me everything" means. */
  const resetFilters = useCallback(() => {
    setSearch("");
    setUsageFilter("all");
    setStatusScope("all");
  }, []);

  const availableIds = useMemo(() => records.map((r) => r.id), [records]);

  return {
    records,
    counts,
    usageFilter,
    setUsageFilter,
    statusScope,
    setStatusScope,
    search,
    setSearch,
    resetFilters,
    isLoading,
    isBusy,
    error,
    notice,
    clearNotice,
    setError,
    load,
    toggleUsed,
    markUsed,
    removeOne,
    removeMany,
    downloadZip,
    availableIds,
  };
}
