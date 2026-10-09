"use client";

import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";

interface ImageCardProps {
  record: ImageRecord;
  /** Opens the fullscreen preview modal (wired by the grid). */
  onOpen?: (record: ImageRecord) => void;
}

/**
 * One processed image on the home page — a framed plate with a caption.
 *
 * Rendered as a button when an opener is provided so clicking opens the same
 * full-viewport viewer the gallery uses; without it (future static sections)
 * it stays a plain figure.
 */
export default function ImageCard({ record, onOpen }: ImageCardProps) {
  const thumb = thumbnailUrl(record.thumbnail_path);
  const cutout = (record.thumbnail_path ?? "").toLowerCase().endsWith(".png");
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  const body = (
    <>
      <div
        className={`relative aspect-[4/3] overflow-hidden border-b border-dashed border-parchment-400 ${
          cutout ? "bg-transparent" : "bg-parchment-200"
        }`}
      >
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={caption}
            loading="lazy"
            className={`h-full w-full transition-transform duration-500 group-hover:scale-[1.03] ${
              cutout ? "object-contain" : "object-cover"
            }`}
          />
        ) : (
          <div className="flex h-full items-center justify-center font-script text-3xl text-parchment-600">
            ✦
          </div>
        )}
        {record.megapixels != null && (
          <span className="absolute left-2 top-2 rounded-sm bg-ink-900/70 px-1.5 py-0.5 font-stamp text-[10px] tracking-wider text-ink-50">
            {record.megapixels.toFixed(1)} MP
          </span>
        )}
      </div>
      {/* Plain div, not figcaption: this block renders inside a <button> too,
          where figure semantics would be invalid. */}
      <div className="px-3 py-2.5">
        <p className="truncate text-sm text-ink-800" title={caption}>
          {caption}
        </p>
        <p className="label-caps mt-0.5">
          {record.stage.replace(/_/g, " ").toLowerCase()}
        </p>
      </div>
    </>
  );

  const baseClass =
    "frame-card group block overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-raised";

  if (!onOpen) {
    return (
      <figure className={baseClass}>
        {body}
      </figure>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(record)}
      className={`${baseClass} w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400`}
      aria-label={`Preview ${caption}`}
    >
      {body}
    </button>
  );
}
