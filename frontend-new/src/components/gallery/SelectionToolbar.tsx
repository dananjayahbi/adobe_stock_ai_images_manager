"use client";

import Button from "@/components/ui/Button";

interface SelectionToolbarProps {
  count: number;
  onSelectAll: () => void;
  onClear: () => void;
  onDownload: () => void;
  /** Direct Adobe-template CSV export for the selection (optional). */
  onExportCsv?: () => void;
  /**
   * Usage state of the selection: which mark buttons make sense. `null`
   * (nothing selected is still on screen) hides both.
   */
  selectedUsage?: "used" | "unused" | "mixed" | null;
  /** Mark the selection used (true) or unused (false). */
  onMarkUsage?: (isUsed: boolean) => void;
  onGroup: () => void;
  onDelete: () => void;
  /** Total images visible, so "select all" can say what it selects. */
  visibleCount: number;
  /** Hide "select all" inside a folder where selecting everything is implied. */
  showSelectAll?: boolean;
}

/**
 * Floating action bar shown while images are selected: download, group,
 * delete. Rendered as a portal-less fixed bar — the gallery has no sticky
 * ancestor with a backdrop-filter, so `fixed` behaves.
 */
export default function SelectionToolbar({
  count,
  onSelectAll,
  onClear,
  onDownload,
  onExportCsv,
  selectedUsage,
  onMarkUsage,
  onGroup,
  onDelete,
  visibleCount,
  showSelectAll = true,
}: SelectionToolbarProps) {
  if (count === 0) return null;

  return (
    <div className="fixed inset-x-0 bottom-5 z-40 flex justify-center px-4">
      <div className="flex flex-wrap items-center justify-center gap-2 rounded-sm border border-parchment-500 bg-ink-900/95 px-4 py-2.5 shadow-raised">
        <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-50">
          {count} selected
        </span>

        <span className="mx-1 h-5 w-px bg-parchment-500/50" aria-hidden="true" />

        <Button variant="secondary" size="sm" onClick={onDownload}>
          ↓ Download
        </Button>
        {onExportCsv && (
          <Button variant="secondary" size="sm" onClick={onExportCsv}>
            ⇪ CSV
          </Button>
        )}
        {/* Only offer the direction the selection can actually move: an
            all-used selection needs "unused", anything else needs "used",
            and a mix offers both. */}
        {onMarkUsage && selectedUsage && selectedUsage !== "used" && (
          <Button variant="secondary" size="sm" onClick={() => onMarkUsage(true)}>
            ✓ Mark used
          </Button>
        )}
        {onMarkUsage && selectedUsage && selectedUsage !== "unused" && (
          <Button variant="secondary" size="sm" onClick={() => onMarkUsage(false)}>
            ○ Mark unused
          </Button>
        )}
        <Button variant="secondary" size="sm" onClick={onGroup}>
          ▸ Group
        </Button>
        <Button variant="danger" size="sm" onClick={onDelete}>
          ✕ Delete
        </Button>

        <span className="mx-1 h-5 w-px bg-parchment-500/50" aria-hidden="true" />

        {showSelectAll && count < visibleCount && (
          <Button variant="ghost" size="sm" onClick={onSelectAll}>
            All {visibleCount}
          </Button>
        )}
        <Button variant="ghost" size="sm" onClick={onClear}>
          Clear
        </Button>
      </div>
    </div>
  );
}
