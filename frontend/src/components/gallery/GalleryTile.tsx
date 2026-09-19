"use client";

import {
  CheckCircle2,
  Circle,
  Download,
  Eye,
  ImageOff,
  Trash2,
} from "lucide-react";
import { useState } from "react";

import {
  formatFileSize,
  getThumbnailUrl,
  type ImageRecord,
} from "@/lib/api";

interface GalleryTileProps {
  record: ImageRecord;
  isSelected: boolean;
  onToggleSelect: (id: string) => void;
  onPreview: (record: ImageRecord) => void;
  onToggleUsed: (record: ImageRecord) => void;
  onDownload: (record: ImageRecord) => void;
  onDelete: (record: ImageRecord) => void;
}

/**
 * A single masonry tile.
 *
 * The image fills the tile width at its natural aspect ratio, and every
 * action is revealed only on hover/focus so the grid stays visually clean.
 */
export default function GalleryTile({
  record,
  isSelected,
  onToggleSelect,
  onPreview,
  onToggleUsed,
  onDownload,
  onDelete,
}: GalleryTileProps) {
  const [failed, setFailed] = useState(false);
  const thumbUrl = getThumbnailUrl(record);
  const showImage = thumbUrl && !failed;
  const isReady = record.status === "READY";

  return (
    <article
      className={`group relative overflow-hidden rounded-xl border bg-navy-900/60 transition-colors ${
        isSelected
          ? "border-accent-500 ring-1 ring-accent-500/40"
          : "border-navy-800 hover:border-navy-600"
      }`}
    >
      {/* Image - fills the tile width, keeps aspect ratio */}
      <button
        type="button"
        onClick={() => onPreview(record)}
        className="relative block w-full bg-navy-950"
        aria-label={`Preview ${record.filename}`}
      >
        {showImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbUrl}
            alt={record.filename}
            loading="lazy"
            className="block w-full object-contain"
            onError={() => setFailed(true)}
          />
        ) : (
          <div className="flex h-40 w-full items-center justify-center">
            <ImageOff className="h-8 w-8 text-navy-700" />
          </div>
        )}

        {/* Hover overlay: metadata strip */}
        <span className="pointer-events-none absolute inset-x-0 bottom-0 flex translate-y-2 flex-col gap-0.5 bg-gradient-to-t from-black/90 via-black/60 to-transparent px-3 pb-3 pt-8 text-left opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100 group-focus-within:translate-y-0 group-focus-within:opacity-100">
          <span className="truncate text-xs font-medium text-navy-50">
            {record.generated_title || record.filename}
          </span>
          <span className="text-[11px] text-navy-300">
            {record.width && record.height
              ? `${record.width}×${record.height}`
              : "—"}
            {record.megapixels != null ? ` · ${record.megapixels} MP` : ""}
            {" · "}
            {formatFileSize(record.file_size_bytes)}
          </span>
        </span>
      </button>

      {/* Selection checkbox - top-left, always visible when selected */}
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          onToggleSelect(record.id);
        }}
        aria-pressed={isSelected}
        aria-label={isSelected ? "Deselect image" : "Select image"}
        className={`absolute left-2 top-2 grid h-7 w-7 place-items-center rounded-md border backdrop-blur transition-all ${
          isSelected
            ? "border-accent-400 bg-accent-500/90 text-white"
            : "border-navy-600/80 bg-navy-950/70 text-navy-300 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 hover:text-white"
        }`}
      >
        {isSelected ? (
          <CheckCircle2 className="h-4 w-4" />
        ) : (
          <Circle className="h-4 w-4" />
        )}
      </button>

      {/* Status / usage badge - top-right, always visible */}
      <div className="absolute right-2 top-2 flex flex-col items-end gap-1">
        {record.is_used ? (
          <span className="rounded-full bg-emerald-500/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-950">
            Used
          </span>
        ) : (
          <span className="rounded-full bg-navy-800/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy-200">
            Unused
          </span>
        )}
        {!isReady && (
          <span className="rounded-full bg-amber-500/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-950">
            {record.status}
          </span>
        )}
      </div>

      {/* Hover action bar */}
      <div className="pointer-events-none absolute inset-x-0 top-1/2 flex -translate-y-1/2 items-center justify-center gap-2 opacity-0 transition-opacity duration-200 group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100">
        <IconAction
          label="Preview"
          onClick={() => onPreview(record)}
          icon={<Eye className="h-4 w-4" />}
        />
        <IconAction
          label={record.is_used ? "Mark as unused" : "Mark as used"}
          onClick={() => onToggleUsed(record)}
          icon={
            record.is_used ? (
              <Circle className="h-4 w-4" />
            ) : (
              <CheckCircle2 className="h-4 w-4" />
            )
          }
        />
        <IconAction
          label={isReady ? "Download" : "Only READY assets can be downloaded"}
          disabled={!isReady}
          onClick={() => onDownload(record)}
          icon={<Download className="h-4 w-4" />}
        />
        <IconAction
          label="Delete"
          danger
          onClick={() => onDelete(record)}
          icon={<Trash2 className="h-4 w-4" />}
        />
      </div>
    </article>
  );
}

function IconAction({
  label,
  icon,
  onClick,
  danger = false,
  disabled = false,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className={`grid h-9 w-9 place-items-center rounded-lg border backdrop-blur transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        danger
          ? "border-red-500/40 bg-red-950/80 text-red-300 hover:bg-red-900/90 hover:text-red-100"
          : "border-navy-600/70 bg-navy-950/80 text-navy-200 hover:bg-navy-800 hover:text-white"
      }`}
    >
      {icon}
    </button>
  );
}
