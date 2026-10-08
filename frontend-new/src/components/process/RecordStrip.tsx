"use client";

import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";
import Badge from "@/components/ui/Badge";

interface RecordStripProps {
  records: ImageRecord[];
  /** Stage keys the current progress marks as failed, to tint the strip. */
  running: boolean;
}

/** Compact result strip: thumbnails + stage chips for the batch's images. */
export default function RecordStrip({ records, running }: RecordStripProps) {
  if (records.length === 0) return null;

  return (
    <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
      {records.map((record) => {
        const thumb = thumbnailUrl(record.thumbnail_path);
        const processed = record.stage_updated_at != null;
        return (
          <li
            key={record.id}
            className={`frame-card overflow-hidden transition-opacity ${
              running && !processed ? "opacity-60" : ""
            }`}
          >
            <div className="aspect-square overflow-hidden border-b border-dashed border-parchment-400 bg-parchment-200">
              {thumb ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={thumb}
                  alt={record.filename}
                  loading="lazy"
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full items-center justify-center font-script text-xl text-parchment-500">
                  ✦
                </div>
              )}
            </div>
            <div className="px-2 py-1.5">
              <p className="truncate text-xs text-ink-800" title={record.filename}>
                {record.filename}
              </p>
              <Badge
                tone={processed ? "success" : "neutral"}
                className="mt-1 !text-[9px]"
              >
                {record.stage.replace(/_/g, " ").toLowerCase()}
              </Badge>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
