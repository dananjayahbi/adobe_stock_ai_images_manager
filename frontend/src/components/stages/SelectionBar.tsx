"use client";

import { CheckSquare, Square, X } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";

export interface SelectionBarProps {
  /** How many records the current bucket holds. */
  totalCount: number;
  selectedCount: number;
  isAllSelected: boolean;
  onSelectAll: () => void;
  onClearSelection: () => void;
  /**
   * Disables the selection controls while a batch runs or records reload — the
   * count on screen is stale at that moment, so acting on it is unsafe.
   */
  actionsDisabled?: boolean;
  /** Primary actions for the current bucket. */
  children?: ReactNode;
}

/**
 * Sticky action bar shown above a record grid.
 *
 * Stays pinned under the header so the batch actions remain reachable while
 * scrolling a long grid.
 */
export function SelectionBar({
  totalCount,
  selectedCount,
  isAllSelected,
  onSelectAll,
  onClearSelection,
  actionsDisabled = false,
  children,
}: SelectionBarProps) {
  const hasSelection = selectedCount > 0;

  return (
    <div className="sticky top-[57px] z-30 -mx-1 flex flex-wrap items-center gap-2 rounded-xl border border-navy-700/50 bg-navy-900/90 px-3 py-2.5 backdrop-blur-xl">
      <Button
        size="sm"
        variant="ghost"
        onClick={isAllSelected ? onClearSelection : onSelectAll}
        disabled={totalCount === 0 || actionsDisabled}
        icon={
          isAllSelected ? (
            <CheckSquare className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <Square className="h-3.5 w-3.5" aria-hidden />
          )
        }
      >
        {isAllSelected ? "Clear" : "Select all"}
      </Button>

      <span className="text-xs tabular-nums text-navy-300">
        {hasSelection && !actionsDisabled ? (
          <>
            <span className="font-semibold text-accent-200">{selectedCount}</span> of{" "}
            {totalCount} selected
          </>
        ) : (
          <>{totalCount} image{totalCount === 1 ? "" : "s"}</>
        )}
      </span>

      {hasSelection && !actionsDisabled ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={onClearSelection}
          icon={<X className="h-3.5 w-3.5" aria-hidden />}
        >
          Deselect
        </Button>
      ) : null}

      <div className="ml-auto flex flex-wrap items-center gap-2">
        {actionsDisabled ? null : children}
      </div>
    </div>
  );
}

export default SelectionBar;
