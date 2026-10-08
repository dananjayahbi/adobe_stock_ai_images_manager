"use client";

import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";

interface GalleryTileProps {
  record: ImageRecord;
  onOpen: (record: ImageRecord) => void;
}

/** Masonry-ish gallery tile: natural aspect ratio, caption on hover. */
export default function GalleryTile({ record, onOpen }: GalleryTileProps) {
  const thumb = thumbnailUrl(record.thumbnail_path);
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  return (
    <button
      type="button"
      onClick={() => onOpen(record)}
      className="frame-card group mb-4 block w-full overflow-hidden text-left transition-all hover:-translate-y-0.5 hover:shadow-raised focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 break-inside-avoid"
    >
      <div className="relative overflow-hidden">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={caption}
            loading="lazy"
            className="w-full transition-transform duration-500 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex aspect-[4/3] items-center justify-center font-script text-3xl text-parchment-500">
            ✦
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 translate-y-full bg-ink-900/80 px-3 py-2 transition-transform duration-300 group-hover:translate-y-0">
          <p className="truncate text-sm text-parchment-100">{caption}</p>
        </div>
      </div>
    </button>
  );
}
