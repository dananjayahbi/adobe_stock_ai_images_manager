"use client";

import { useCallback, useMemo, useState } from "react";

/**
 * Multi-select state for a stage's image grid.
 *
 * Selection is keyed by record id so it survives the 4-second polling refresh:
 * a record that briefly disappears from the list keeps its selection, and only
 * an explicit `prune` (or `clear`) removes it.
 */
export function useStageSelection() {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const isSelected = useCallback(
    (id: string) => selectedSet.has(id),
    [selectedSet]
  );

  const toggle = useCallback((id: string) => {
    setSelectedIds((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id]
    );
  }, []);

  const selectMany = useCallback((ids: string[]) => {
    setSelectedIds((current) => Array.from(new Set([...current, ...ids])));
  }, []);

  const deselectMany = useCallback((ids: string[]) => {
    const remove = new Set(ids);
    setSelectedIds((current) => current.filter((id) => !remove.has(id)));
  }, []);

  /** Replace the selection with exactly these ids. */
  const selectOnly = useCallback((ids: string[]) => {
    setSelectedIds(Array.from(new Set(ids)));
  }, []);

  const clear = useCallback(() => setSelectedIds([]), []);

  /** Drop ids that no longer exist, e.g. after a delete. */
  const prune = useCallback((availableIds: string[]) => {
    const available = new Set(availableIds);
    setSelectedIds((current) => {
      const next = current.filter((id) => available.has(id));
      // Preserve identity when nothing changed, so dependents do not re-render.
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
