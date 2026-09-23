"use client";

import { ImageOff, Loader2 } from "lucide-react";

import type { ImageRecord } from "@/lib/api";

import GalleryTile from "./GalleryTile";

interface GalleryMasonryGridProps {
  records: ImageRecord[];
  isLoading: boolean;
  isSelected: (id: string) => boolean;
  onToggleSelect: (id: string) => void;
  onPreview: (record: ImageRecord) => void;
  onToggleUsed: (record: ImageRecord) => void;
  onDownload: (record: ImageRecord) => void;
  onDelete: (record: ImageRecord) => void;
  /**
   * Copy for the empty state.
   *
   * Supplied by the page because the *cause* differs: an empty search result and
   * an empty gallery need different advice, and a single generic "no images"
   * message makes an active search look like an empty library.
   */
  emptyState?: { title: string; description: string };
}

/** CSS-columns masonry grid of gallery tiles. */
export default function GalleryMasonryGrid({
  records,
  isLoading,
  isSelected,
  onToggleSelect,
  onPreview,
  onToggleUsed,
  onDownload,
  onDelete,
  emptyState,
}: GalleryMasonryGridProps) {
  if (isLoading && records.length === 0) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-navy-800 py-16 text-navy-400">
        <Loader2 className="h-5 w-5 animate-spin" />
        Loading gallery…
      </div>
    );
  }

  if (records.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-navy-800 px-6 py-16 text-center text-navy-400">
        <ImageOff className="h-7 w-7 text-navy-700" />
        <p className="text-sm text-navy-200">
          {emptyState?.title ?? "No staged images match the current filter."}
        </p>
        {emptyState?.description ? (
          <p className="max-w-md text-xs text-navy-500">{emptyState.description}</p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="masonry-grid">
      {records.map((record) => (
        <div key={record.id} className="masonry-item">
          <GalleryTile
            record={record}
            isSelected={isSelected(record.id)}
            onToggleSelect={onToggleSelect}
            onPreview={onPreview}
            onToggleUsed={onToggleUsed}
            onDownload={onDownload}
            onDelete={onDelete}
          />
        </div>
      ))}
    </div>
  );
}
