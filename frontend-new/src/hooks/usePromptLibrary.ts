"use client";

/**
 * The Prompt Library grid's data layer: list, filters, debounced search, and
 * the status/delete mutations.
 *
 * Follows the polling-safe loader discipline used elsewhere in the app: a
 * monotonic request id means a filter change during an in-flight request can
 * never be clobbered by an older response landing late. Search is debounced
 * here rather than in the component so the input stays instant while the
 * request waits.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import {
  deletePrompt,
  fetchPrompts,
  updatePrompt,
  type Prompt,
  type PromptFilter,
  type PromptListResponse,
} from "@/lib/prompts";

/** Debounce before a keystroke becomes a request. */
const SEARCH_DEBOUNCE_MS = 300;

export interface PromptLibraryTotals {
  total: number;
  used: number;
  unused: number;
  archived: number;
}

export interface UsePromptLibraryResult {
  prompts: Prompt[];
  totals: PromptLibraryTotals;
  /** The committed filter tab. */
  filter: PromptFilter;
  setFilter: (next: PromptFilter) => void;
  /** The live search-box text (updates immediately). */
  query: string;
  setQuery: (next: string) => void;
  isLoading: boolean;
  /** Id of the prompt currently being mutated, for row-level spinners. */
  busyPromptId: string | null;
  error: string | null;
  notice: string | null;
  clearNotice: () => void;
  /** Reload the library. `silent` skips the loading flag. */
  reload: (silent?: boolean) => Promise<void>;
  /** Mark used (`USED`) or unused (`DRAFT`). */
  setPromptStatus: (promptId: string, status: Prompt["status"]) => Promise<void>;
  removePrompt: (promptId: string) => Promise<void>;
}

const EMPTY_TOTALS: PromptLibraryTotals = {
  total: 0,
  used: 0,
  unused: 0,
  archived: 0,
};

export function usePromptLibrary(): UsePromptLibraryResult {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [totals, setTotals] = useState<PromptLibraryTotals>(EMPTY_TOTALS);
  const [filter, setFilter] = useState<PromptFilter>("all");
  const [query, setQuery] = useState("");
  /** The value that actually reaches the request, after the debounce. */
  const [committedQuery, setCommittedQuery] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [busyPromptId, setBusyPromptId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const requestId = useRef(0);
  // Read inside `reload`; refs keep the callback stable so the effect below
  // does not restart on every keystroke.
  const filterRef = useRef(filter);
  filterRef.current = filter;
  const queryRef = useRef(committedQuery);
  queryRef.current = committedQuery;

  const reload = useCallback(async (silent = false) => {
    const id = ++requestId.current;
    if (!silent) setLoading(true);
    try {
      const listing: PromptListResponse = await fetchPrompts(
        filterRef.current,
        queryRef.current
      );
      if (id !== requestId.current) return;
      setPrompts(listing.items);
      // Counts as the server reports them, status axis only — the binding
      // counts are still on the response but no tab reads them.
      setTotals({
        total: listing.total,
        used: listing.used,
        unused: listing.unused,
        archived: listing.archived,
      });
      setError(null);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : "Failed to load prompts.");
    } finally {
      if (id === requestId.current && !silent) setLoading(false);
    }
  }, []);

  // Debounce the search box into the committed query.
  useEffect(() => {
    const timer = setTimeout(
      () => setCommittedQuery(query.trim()),
      SEARCH_DEBOUNCE_MS
    );
    return () => clearTimeout(timer);
  }, [query]);

  // Refetch on tab change, committed-search change, or first mount.
  useEffect(() => {
    void reload();
  }, [reload, filter, committedQuery]);

  const clearNotice = useCallback(() => setNotice(null), []);

  const setPromptStatus = useCallback(
    async (promptId: string, status: Prompt["status"]) => {
      setBusyPromptId(promptId);
      setError(null);
      try {
        await updatePrompt(promptId, { status });
        await reload(true);
        setNotice(status === "USED" ? "Marked used." : "Marked unused.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not update the prompt.");
      } finally {
        setBusyPromptId(null);
      }
    },
    [reload]
  );

  const removePrompt = useCallback(
    async (promptId: string) => {
      setBusyPromptId(promptId);
      setError(null);
      try {
        await deletePrompt(promptId);
        await reload(true);
        setNotice("Prompt deleted.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not delete the prompt.");
      } finally {
        setBusyPromptId(null);
      }
    },
    [reload]
  );

  return {
    prompts,
    totals,
    filter,
    setFilter,
    query,
    setQuery,
    isLoading,
    busyPromptId,
    error,
    notice,
    clearNotice,
    reload,
    setPromptStatus,
    removePrompt,
  };
}
