"use client";

import { useFolderDrop } from "@/hooks/useFolderDrop";
import type { GalleryGroup } from "@/lib/types";

interface GroupCardProps {
  group: GalleryGroup;
  onOpen: (group: GalleryGroup) => void;
  onRename: (group: GalleryGroup) => void;
  onDelete: (group: GalleryGroup) => void;
  /**
   * When provided the card accepts a dropped selection of images and moves
   * them into this folder (gallery drag-and-drop).
   */
  onDropRecords?: (recordIds: string[]) => void;
}

/**
 * A folder tile in the gallery. Folder cards sit *outside* the image filters
 * by design: filtering never hides a folder, only the images inside one.
 */
export default function GroupCard({
  group,
  onOpen,
  onRename,
  onDelete,
  onDropRecords,
}: GroupCardProps) {
  const drop = useFolderDrop({
    droppable: onDropRecords !== undefined,
    onDropRecords: onDropRecords ?? (() => {}),
  });

  return (
    <div
      onDragEnter={drop.onDragEnter}
      onDragOver={drop.onDragOver}
      onDragLeave={drop.onDragLeave}
      onDrop={drop.onDrop}
      className={`frame-card group relative mb-4 block w-full break-inside-avoid transition-all hover:-translate-y-0.5 hover:shadow-raised ${
        drop.dragOver ? "ring-2 ring-oxblood-400 shadow-raised" : ""
      }`}
    >
      <button
        type="button"
        onClick={() => onOpen(group)}
        className="block w-full px-4 py-5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400"
        aria-label={`Open folder ${group.name}`}
      >
        <div className="flex items-center gap-3">
          {/* Folder glyph, drawn rather than imported. */}
          <span
            aria-hidden="true"
            className="flex h-10 w-12 shrink-0 items-center justify-center rounded-sm border border-brass-400/60 bg-brass-300/15 font-script text-xl text-brass-300"
          >
            ▸
          </span>
          <div className="min-w-0">
            <p className="truncate font-display text-base text-ink-800" title={group.name}>
              {group.name}
            </p>
            <p className="font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
              {group.image_count} image{group.image_count !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
      </button>

      {/* Drop affordance: shown only while a gallery selection hovers. */}
      {drop.dragOver && (
        <p className="pointer-events-none absolute inset-x-0 bottom-0 bg-oxblood-500 px-3 py-1 text-center font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-50">
          {drop.dropCount > 0
            ? `Move ${drop.dropCount} image${drop.dropCount === 1 ? "" : "s"} here`
            : "Move images here"}
        </p>
      )}

      <div className="absolute right-2 top-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        <button
          type="button"
          onClick={() => onRename(group)}
          aria-label={`Rename ${group.name}`}
          className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 bg-ink-900/70 font-stamp text-[11px] text-ink-50 hover:bg-ink-900"
        >
          ✎
        </button>
        <button
          type="button"
          onClick={() => onDelete(group)}
          aria-label={`Delete folder ${group.name}`}
          className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 bg-ink-900/70 font-stamp text-[11px] text-ink-50 hover:bg-ink-900"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
