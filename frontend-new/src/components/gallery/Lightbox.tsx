"use client";

import { useEffect, useState } from "react";
import { thumbnailUrl } from "@/lib/client";
import type { ImageRecord } from "@/lib/types";
import Modal from "@/components/ui/Modal";
import Badge from "@/components/ui/Badge";

interface LightboxProps {
  record: ImageRecord | null;
  onClose: () => void;
  onNavigate: (direction: -1 | 1) => void;
}

/** Full-size preview with keyboard navigation. */
export default function Lightbox({ record, onClose, onNavigate }: LightboxProps) {
  useEffect(() => {
    if (!record) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "ArrowLeft") onNavigate(-1);
      if (event.key === "ArrowRight") onNavigate(1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [record, onClose, onNavigate]);

  if (!record) return null;

  const thumb = thumbnailUrl(record.thumbnail_path);
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  return (
    <Modal open={!!record} onClose={onClose} width="max-w-4xl">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="label-caps">Plate</p>
            <h2 className="mt-0.5 truncate font-display text-xl text-ink-800">
              {caption}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="font-stamp text-xs uppercase tracking-[0.14em] text-ink-400 hover:text-ink-800"
          >
            Close ✕
          </button>
        </div>
      </div>

      <div className="bg-parchment-200 px-6 py-5">
        {thumb && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumb}
            alt={caption}
            className="mx-auto max-h-[60vh] rounded-sm border border-parchment-400 bg-parchment-50 object-contain p-1 shadow-card"
          />
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-dashed border-parchment-400 px-6 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="info">{record.stage.replace(/_/g, " ")}</Badge>
          {record.megapixels != null && (
            <Badge>{record.megapixels.toFixed(1)} MP</Badge>
          )}
          {record.acceptance_score != null && (
            <Badge tone={record.acceptance_score >= 0.8 ? "success" : "warn"}>
              {(record.acceptance_score * 100).toFixed(0)}%
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onNavigate(-1)}
            className="rounded-sm border border-parchment-500 px-3 py-1.5 font-stamp text-xs uppercase tracking-[0.14em] text-ink-600 hover:bg-parchment-200"
          >
            ← Prev
          </button>
          <button
            type="button"
            onClick={() => onNavigate(1)}
            className="rounded-sm border border-parchment-500 px-3 py-1.5 font-stamp text-xs uppercase tracking-[0.14em] text-ink-600 hover:bg-parchment-200"
          >
            Next →
          </button>
        </div>
      </div>
    </Modal>
  );
}
