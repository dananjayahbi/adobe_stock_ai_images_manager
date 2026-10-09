"use client";

import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";

/** One processed image on the home page — a framed plate with a caption. */
export default function ImageCard({ record }: { record: ImageRecord }) {
  const thumb = thumbnailUrl(record.thumbnail_path);
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  return (
    <figure className="frame-card group overflow-hidden transition-all hover:-translate-y-0.5 hover:shadow-raised">
      <div className="relative aspect-[4/3] overflow-hidden border-b border-dashed border-parchment-400 bg-parchment-200">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={caption}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]"
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
      <figcaption className="px-3 py-2.5">
        <p className="truncate text-sm text-ink-800" title={caption}>
          {caption}
        </p>
        <p className="label-caps mt-0.5">
          {record.stage.replace(/_/g, " ").toLowerCase()}
        </p>
      </figcaption>
    </figure>
  );
}
