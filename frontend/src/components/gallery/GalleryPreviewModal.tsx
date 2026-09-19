"use client";

import { CheckCircle2, Circle, Download, Trash2, X } from "lucide-react";
import { useEffect } from "react";

import { getDownloadUrl, getThumbnailUrl, type ImageRecord } from "@/lib/api";

interface GalleryPreviewModalProps {
  record: ImageRecord | null;
  onClose: () => void;
  onToggleUsed: (record: ImageRecord) => void;
  onDownload: (record: ImageRecord) => void;
  onDelete: (record: ImageRecord) => void;
}

/** Lightweight preview modal for a gallery asset. */
export default function GalleryPreviewModal({
  record,
  onClose,
  onToggleUsed,
  onDownload,
  onDelete,
}: GalleryPreviewModalProps) {
  useEffect(() => {
    if (!record) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [record, onClose]);

  if (!record) return null;

  const thumbUrl = getThumbnailUrl(record);
  const isReady = record.status === "READY";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`Preview ${record.filename}`}
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-navy-800 bg-navy-950 lg:flex-row"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex flex-1 items-center justify-center overflow-auto bg-navy-900 p-4">
          {thumbUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumbUrl}
              alt={record.filename}
              className="max-h-[80vh] w-auto object-contain"
            />
          ) : (
            <p className="text-sm text-navy-400">No thumbnail available.</p>
          )}
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-4 overflow-y-auto border-t border-navy-800 p-5 lg:w-80 lg:border-l lg:border-t-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-navy-50">
                {record.generated_title || record.filename}
              </h2>
              <p className="mt-0.5 font-mono text-[11px] text-navy-400">
                {record.filename}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close preview"
              className="rounded-md p-1 text-navy-400 transition-colors hover:text-navy-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <dl className="space-y-1.5 text-xs">
            <Row label="Status" value={record.status} />
            <Row label="Usage" value={record.is_used ? "Used" : "Unused"} />
            <Row
              label="Dimensions"
              value={
                record.width && record.height
                  ? `${record.width}×${record.height}`
                  : "—"
              }
            />
            <Row
              label="Megapixels"
              value={record.megapixels != null ? `${record.megapixels}` : "—"}
            />
            <Row
              label="Confidence"
              value={
                record.semantic_confidence_score != null
                  ? `${Math.round(record.semantic_confidence_score * 100)}%`
                  : "—"
              }
            />
          </dl>

          {record.generated_description && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wide text-navy-400">
                Description
              </p>
              <p className="text-xs leading-relaxed text-navy-200">
                {record.generated_description}
              </p>
            </div>
          )}

          {record.generated_keywords && record.generated_keywords.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] uppercase tracking-wide text-navy-400">
                Keywords ({record.generated_keywords.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {record.generated_keywords.map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-full border border-navy-700 px-2 py-0.5 text-[11px] text-navy-200"
                  >
                    {keyword}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-auto flex flex-col gap-2 pt-2">
            <button
              type="button"
              onClick={() => onToggleUsed(record)}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-navy-700 px-3 py-2 text-xs font-medium text-navy-100 transition-colors hover:border-navy-400"
            >
              {record.is_used ? (
                <Circle className="h-3.5 w-3.5" />
              ) : (
                <CheckCircle2 className="h-3.5 w-3.5" />
              )}
              {record.is_used ? "Mark as unused" : "Mark as used"}
            </button>

            <a
              href={isReady ? getDownloadUrl(record.id) : undefined}
              onClick={(event) => {
                event.preventDefault();
                if (isReady) onDownload(record);
              }}
              aria-disabled={!isReady}
              className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-2 text-xs font-semibold transition-colors ${
                isReady
                  ? "bg-accent-600 text-white hover:bg-accent-500"
                  : "cursor-not-allowed bg-navy-800 text-navy-400"
              }`}
            >
              <Download className="h-3.5 w-3.5" />
              {isReady ? "Download" : "Not upload-ready"}
            </a>

            <button
              type="button"
              onClick={() => onDelete(record)}
              className="inline-flex items-center justify-center gap-1.5 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-300 transition-colors hover:border-red-400 hover:text-red-100"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-navy-800/70 pb-1.5">
      <dt className="text-navy-400">{label}</dt>
      <dd className="font-medium text-navy-100">{value}</dd>
    </div>
  );
}
