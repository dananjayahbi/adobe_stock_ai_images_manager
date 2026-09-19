"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * Manages multi-select state for the gallery grid.
 *
 * Selection is id-based so it survives the 3s polling refresh, and stale ids
 * are pruned whenever the visible record set changes.
 */
export function useGallerySelection() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const isSelected = useCallback(
    (id: string) => selectedSet.has(id),
    [selectedSet]
  );

  const toggle = useCallback((id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((value) => value !== id) : [...prev, id]
    );
  }, []);

  const selectMany = useCallback((ids: string[]) => {
    setSelectedIds((prev) => Array.from(new Set([...prev, ...ids])));
  }, []);

  const deselectMany = useCallback((ids: string[]) => {
    const remove = new Set(ids);
    setSelectedIds((prev) => prev.filter((value) => !remove.has(value)));
  }, []);

  const toggleMany = useCallback((ids: string[]) => {
    setSelectedIds((prev) => {
      const everySelected = ids.length > 0 && ids.every((id) => prev.includes(id));
      if (everySelected) {
        const remove = new Set(ids);
        return prev.filter((value) => !remove.has(value));
      }
      return Array.from(new Set([...prev, ...ids]));
    });
  }, []);

  const clear = useCallback(() => setSelectedIds([]), []);

  /** Drop ids that no longer exist in the supplied record set. */
  const prune = useCallback((validIds: string[]) => {
    const valid = new Set(validIds);
    setSelectedIds((prev) => {
      const next = prev.filter((value) => valid.has(value));
      return next.length === prev.length ? prev : next;
    });
  }, []);

  return {
    selectedIds,
    selectedSet,
    count: selectedIds.length,
    isSelected,
    toggle,
    selectMany,
    deselectMany,
    toggleMany,
    clear,
    prune,
  };
}
