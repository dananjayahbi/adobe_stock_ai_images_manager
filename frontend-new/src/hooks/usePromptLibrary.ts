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
  assignPromptGroup,
  deletePrompt,
  fetchPrompts,
  updatePrompt,
  type Prompt,
  type PromptFilter,
  type PromptGroup,
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
  /** Folder filter — committed immediately (chips, not keystrokes). */
  group: string;
  setGroup: (next: string) => void;
  /** Folders with their counts, for the filter chips. */
  groups: PromptGroup[];
  /** Multi-select (batch grouping): ids currently ticked. */
  selectedIds: string[];
  toggleSelected: (promptId: string) => void;
  clearSelection: () => void;
  /** Move the selection into a folder ("" ungroups). */
  groupSelection: (groupName: string) => Promise<void>;
  isGrouping: boolean;
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
  const [groups, setGroups] = useState<PromptGroup[]>([]);
  const [filter, setFilter] = useState<PromptFilter>("all");
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isGrouping, setGrouping] = useState(false);
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
  const groupRef = useRef(group);
  groupRef.current = group;

  const reload = useCallback(async (silent = false) => {
    const id = ++requestId.current;
    if (!silent) setLoading(true);
    try {
      const listing: PromptListResponse = await fetchPrompts(
        filterRef.current,
        queryRef.current,
        groupRef.current
      );
      if (id !== requestId.current) return;
      setPrompts(listing.items);
      setGroups(listing.groups ?? []);
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

  // Refetch on tab change, committed-search change, folder change, or first
  // mount. A filter change also clears the selection: ticked prompts may no
  // longer be on screen, and grouping an invisible selection is a mis-click
  // waiting to happen.
  useEffect(() => {
    setSelectedIds([]);
    void reload();
  }, [reload, filter, committedQuery, group]);

  const clearNotice = useCallback(() => setNotice(null), []);

  const toggleSelected = useCallback((promptId: string) => {
    setSelectedIds((current) =>
      current.includes(promptId)
        ? current.filter((id) => id !== promptId)
        : [...current, promptId]
    );
  }, []);

  const clearSelection = useCallback(() => setSelectedIds([]), []);

  const groupSelection = useCallback(
    async (groupName: string) => {
      if (selectedIds.length === 0) return;
      setGrouping(true);
      setError(null);
      try {
        const result = await assignPromptGroup(selectedIds, groupName);
        // A selection now outside the active folder filter would be invisible
        // after the move, so the selection is dropped either way.
        setSelectedIds([]);
        await reload(true);
        const where = result.group_name
          ? `moved to “${result.group_name}”`
          : result.updated === 1
            ? "removed from its folder"
            : "removed from their folders";
        const missing =
          result.missing.length > 0
            ? ` (${result.missing.length} unknown id${
                result.missing.length === 1 ? "" : "s"
              } skipped)`
            : "";
        setNotice(
          `${result.updated} prompt${result.updated === 1 ? "" : "s"} ${where}.${missing}`
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not update the folder.");
      } finally {
        setGrouping(false);
      }
    },
    [reload, selectedIds]
  );

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
    group,
    setGroup,
    groups,
    selectedIds,
    toggleSelected,
    clearSelection,
    groupSelection,
    isGrouping,
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
