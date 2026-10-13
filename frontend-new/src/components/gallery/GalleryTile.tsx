"use client";

import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";

interface GalleryTileProps {
  record: ImageRecord;
  onOpen: (record: ImageRecord) => void;
  /** Multi-select mode: clicking the tile toggles selection instead of opening. */
  selected?: boolean;
  onToggleSelect?: (record: ImageRecord) => void;
  /** Select mode: the checkbox is always visible, clicking ticks the tile. */
  selectMode?: boolean;
}

/** True when the thumbnail is a transparent PNG cut-out. */
function isCutout(record: ImageRecord): boolean {
  return (record.thumbnail_path ?? "").toLowerCase().endsWith(".png");
}

/**
 * Masonry-ish gallery tile: natural aspect ratio, caption on hover.
 *
 * Cut-outs render as a transparent PNG over the card's own background — no
 * white plate — so the leather shows through the transparent regions, which
 * is exactly how Adobe will display an alpha PNG.
 */
export default function GalleryTile({
  record,
  onOpen,
  selected = false,
  onToggleSelect,
  selectMode = false,
}: GalleryTileProps) {
  const thumb = thumbnailUrl(record.thumbnail_path);
  const cutout = isCutout(record);
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  return (
    <div
      data-record-id={record.id}
      className={`frame-card group relative mb-4 block w-full overflow-hidden break-inside-avoid transition-all hover:-translate-y-0.5 hover:shadow-raised ${
        selected ? "ring-2 ring-oxblood-400" : ""
      } ${selectMode ? "cursor-pointer" : ""}`}
    >
      <button
        type="button"
        onClick={() => (selectMode && onToggleSelect ? onToggleSelect(record) : onOpen(record))}
        className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400"
        aria-label={`Preview ${caption}`}
      >
        <div className={`relative overflow-hidden ${cutout ? "bg-transparent" : ""}`}>
          {thumb ? (
            // draggable={false}: a native image drag fires pointercancel and
            // kills the marquee's pointer sequence mid-box (select mode).
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumb}
              alt={caption}
              loading="lazy"
              draggable={false}
              className={`w-full transition-transform duration-500 group-hover:scale-[1.03] ${
                cutout ? "object-contain" : ""
              }`}
            />
          ) : (
            <div className="flex aspect-[4/3] items-center justify-center font-script text-3xl text-parchment-600">
              ✦
            </div>
          )}
          <div className="absolute inset-x-0 bottom-0 translate-y-full bg-ink-900/80 px-3 py-2 transition-transform duration-300 group-hover:translate-y-0">
            <p className="truncate text-sm text-ink-50">{caption}</p>
          </div>
        </div>
      </button>

      {onToggleSelect && (
        <button
          type="button"
          onClick={() => onToggleSelect(record)}
          aria-label={`Select ${caption}`}
          aria-pressed={selected}
          className={`absolute left-2 top-2 flex h-6 w-6 items-center justify-center rounded-sm border font-stamp text-xs transition-opacity ${
            selected
              ? "border-oxblood-500 bg-oxblood-500 text-ink-50 opacity-100"
              : selectMode
                ? "border-parchment-500 bg-ink-900/70 text-ink-50 opacity-100"
                : "border-parchment-500 bg-ink-900/70 text-ink-50 opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          }`}
        >
          {selected ? "✓" : ""}
        </button>
      )}

      {/* Already delivered: the stamp mirrors the selection toolbar's mark,
          so which images are used is answerable at a glance (the default
          usage filter is "any"). */}
      {record.is_used && (
        <span
          aria-label="Marked as used"
          className="absolute right-2 top-2 rounded-sm border border-brass-400/70 bg-ink-900/80 px-1.5 py-0.5 font-stamp text-[10px] uppercase tracking-[0.14em] text-brass-300"
        >
          Used
        </span>
      )}
    </div>
  );
}
