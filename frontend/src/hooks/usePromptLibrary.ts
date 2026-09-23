"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  bindPrompt,
  createPrompt,
  deletePrompt,
  fetchPrompts,
  updatePrompt,
  type Prompt,
  type PromptDraft,
  type PromptFilter,
} from "@/lib/prompts";

/**
 * State for the Prompt Library sidebar.
 *
 * Mirrors the polling discipline used elsewhere in the app: a monotonic request
 * id so a slow response cannot overwrite a newer one, and no "in-flight" guard
 * — a filter change during a poll must never be dropped.
 *
 * The hook owns the *library*; binding is exposed as a callback so the page can
 * refresh its record list from a single place.
 */
export interface UsePromptLibraryResult {
  prompts: Prompt[];
  totals: { total: number; used: number; unused: number };
  filter: PromptFilter;
  setFilter: (next: PromptFilter) => void;
  isLoading: boolean;
  /** Id of the prompt currently being mutated, for row-level spinners. */
  busyPromptId: string | null;
  error: string | null;
  setError: (message: string | null) => void;
  notice: string | null;
  clearNotice: () => void;
  /** Reload the library. `silent` skips the loading flag (polling). */
  reload: (silent?: boolean) => Promise<void>;
  savePrompt: (draft: PromptDraft, promptId?: string) => Promise<Prompt>;
  removePrompt: (promptId: string) => Promise<void>;
  setPromptStatus: (promptId: string, status: Prompt["status"]) => Promise<void>;
  /**
   * Bind images to a prompt (or unbind). Returns the number of records that
   * changed, so the caller can word its own confirmation.
   */
  bind: (
    promptId: string,
    recordIds: string[],
    unbind?: boolean
  ) => Promise<number>;
}

const POLL_INTERVAL_MS = 8000;

/**
 * @param enabled When false the library is inert: no fetch, no polling. The
 *   Collector mounts this hook unconditionally (hooks cannot be called
 *   conditionally) but only *uses* it in Advanced mode, so this flag is what
 *   stops Quick mode from making pointless requests every 8 seconds.
 */
export function usePromptLibrary(enabled = true): UsePromptLibraryResult {
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [totals, setTotals] = useState({ total: 0, used: 0, unused: 0 });
  const [filter, setFilter] = useState<PromptFilter>("all");
  const [isLoading, setLoading] = useState(true);
  const [busyPromptId, setBusyPromptId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const requestId = useRef(0);
  // The filter is read inside `reload`; a ref keeps the callback stable so the
  // polling effect does not restart on every filter change.
  const filterRef = useRef(filter);
  filterRef.current = filter;
  // Same reasoning for `enabled`: it is read inside the stable `reload`.
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;

  const reload = useCallback(
    async (silent = false) => {
      if (!enabledRef.current) return;
      const id = ++requestId.current;
      if (!silent) setLoading(true);
      try {
        const listing = await fetchPrompts(filterRef.current);
        if (id !== requestId.current) return;
        setPrompts(listing.items);
        setTotals({
          total: listing.total,
          used: listing.used,
          unused: listing.unused,
        });
        setError(null);
      } catch (err) {
        if (id !== requestId.current) return;
        setError(err instanceof Error ? err.message : "Failed to load prompts.");
      } finally {
        if (id === requestId.current && !silent) setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!enabled) return;
    void reload();
  }, [enabled, reload, filter]);

  useEffect(() => {
    if (!enabled) return;
    const interval = setInterval(() => void reload(true), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [enabled, reload]);

  const clearNotice = useCallback(() => setNotice(null), []);

  const savePrompt = useCallback(
    async (draft: PromptDraft, promptId?: string) => {
      setBusyPromptId(promptId ?? "new");
      setError(null);
      try {
        const saved = promptId
          ? await updatePrompt(promptId, draft)
          : await createPrompt(draft);
        await reload(true);
        setNotice(promptId ? "Prompt updated." : "Prompt added.");
        return saved;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save the prompt.");
        throw err;
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
        const result = await deletePrompt(promptId);
        await reload(true);
        setNotice(
          result.unbound > 0
            ? `Prompt deleted. ${result.unbound} image(s) kept and unbound.`
            : "Prompt deleted."
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not delete the prompt.");
        throw err;
      } finally {
        setBusyPromptId(null);
      }
    },
    [reload]
  );

  const setPromptStatus = useCallback(
    async (promptId: string, status: Prompt["status"]) => {
      setBusyPromptId(promptId);
      setError(null);
      try {
        await updatePrompt(promptId, { status });
        await reload(true);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not update the prompt.");
      } finally {
        setBusyPromptId(null);
      }
    },
    [reload]
  );

  const bind = useCallback(
    async (promptId: string, recordIds: string[], unbind = false) => {
      if (recordIds.length === 0) {
        setError("Select at least one image to bind.");
        return 0;
      }
      setBusyPromptId(promptId);
      setError(null);
      try {
        const result = await bindPrompt(promptId, recordIds, unbind);
        await reload(true);
        setNotice(
          unbind
            ? `Unbound ${result.updated} image(s).`
            : `Bound ${result.updated} image(s) to "${result.prompt.title}".`
        );
        return result.updated;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not bind the images.");
        throw err;
      } finally {
        setBusyPromptId(null);
      }
    },
    [reload]
  );

  const value = useMemo(
    () => ({
      prompts,
      totals,
      filter,
      setFilter,
      isLoading,
      busyPromptId,
      error,
      setError,
      notice,
      clearNotice,
      reload,
      savePrompt,
      removePrompt,
      setPromptStatus,
      bind,
    }),
    [
      prompts,
      totals,
      filter,
      isLoading,
      busyPromptId,
      error,
      notice,
      clearNotice,
      reload,
      savePrompt,
      removePrompt,
      setPromptStatus,
      bind,
    ]
  );

  return value;
}
