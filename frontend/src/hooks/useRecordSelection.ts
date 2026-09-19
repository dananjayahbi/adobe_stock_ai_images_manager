"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * Selection keyed by record id.
 *
 * Keying by id (rather than by index or object identity) is what lets the
 * selection survive the 4 s poll: the record objects are replaced on every
 * refresh, but the ids are stable.
 */
export function useRecordSelection() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const isSelected = useCallback((id: string) => selectedSet.has(id), [selectedSet]);

  const toggle = useCallback((id: string) => {
    setSelectedIds((current) =>
      current.includes(id) ? current.filter((value) => value !== id) : [...current, id]
    );
  }, []);

  const selectMany = useCallback((ids: string[]) => {
    setSelectedIds((current) => Array.from(new Set([...current, ...ids])));
  }, []);

  const deselectMany = useCallback((ids: string[]) => {
    const remove = new Set(ids);
    setSelectedIds((current) => current.filter((value) => !remove.has(value)));
  }, []);

  const selectOnly = useCallback((ids: string[]) => {
    setSelectedIds(Array.from(new Set(ids)));
  }, []);

  const clear = useCallback(() => setSelectedIds([]), []);

  /** Drop ids that no longer exist, e.g. after a delete. */
  const prune = useCallback((availableIds: string[]) => {
    const available = new Set(availableIds);
    setSelectedIds((current) => {
      const next = current.filter((value) => available.has(value));
      return next.length === current.length ? current : next;
    });
  }, []);

  return {
    selectedIds,
    count: selectedIds.length,
    isSelected,
    toggle,
    selectMany,
    deselectMany,
    selectOnly,
    clear,
    prune,
  };
}

export type RecordSelection = ReturnType<typeof useRecordSelection>;
