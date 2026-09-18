"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Maximize2,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  formatFileSize,
  getThumbnailUrl,
  type ImageRecord,
} from "@/lib/api";

interface InspectionModalProps {
  record: ImageRecord | null;
  isOpen: boolean;
  onClose: () => void;
  onApprove?: (id: string, overrides?: { override_title?: string }) => void;
  isApproving?: boolean;
}

function flagsToList(flags: ImageRecord["semantic_flags"]): string[] {
  if (!flags) return [];
  if (Array.isArray(flags)) return flags.map(String);
  return Object.entries(flags).map(([key, value]) => `${key}: ${String(value)}`);
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-zinc-800 py-2 text-sm">
      <span className="text-zinc-500">{label}</span>
      <span className="text-right font-medium text-zinc-200">{value}</span>
    </div>
  );
}

export default function InspectionModal({
  record,
  isOpen,
  onClose,
  onApprove,
  isApproving = false,
}: InspectionModalProps) {
  const [zoom, setZoom] = useState(1);
  const [titleDraft, setTitleDraft] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setZoom(1);
    setTitleDraft(record?.generated_title ?? "");
  }, [isOpen, record?.id, record?.generated_title]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !record) return null;

  const thumbUrl = getThumbnailUrl(record);
  const flagList = flagsToList(record.semantic_flags);
  const confidence = record.semantic_confidence_score;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Inspect ${record.filename}`}
    >
      <div
        className="flex max-h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950 lg:flex-row"
        onClick={(event) => event.stopPropagation()}
      >
        {/* Left: viewer */}
        <div className="relative flex flex-1 items-center justify-center overflow-auto bg-zinc-900 p-4">
          <div className="absolute left-4 top-4 z-10 flex gap-2">
            <button
              type="button"
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
              className="rounded-md bg-zinc-950/80 p-2 text-zinc-300 hover:text-white"
              aria-label="Zoom out"
            >
              <ZoomOut className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom((z) => Math.min(4, z + 0.25))}
              className="rounded-md bg-zinc-950/80 p-2 text-zinc-300 hover:text-white"
              aria-label="Zoom in"
            >
              <ZoomIn className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setZoom(1)}
              className="rounded-md bg-zinc-950/80 p-2 text-zinc-300 hover:text-white"
              aria-label="Reset zoom"
            >
              <Maximize2 className="h-4 w-4" />
            </button>
          </div>

          {thumbUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={thumbUrl}
              alt={record.filename}
              style={{ transform: `scale(${zoom})` }}
              className="max-h-[80vh] origin-center object-contain transition-transform"
            />
          ) : (
            <p className="text-sm text-zinc-600">No preview available.</p>
          )}
        </div>

        {/* Right: details */}
        <div className="flex w-full flex-col overflow-y-auto border-t border-zinc-800 p-6 lg:w-[26rem] lg:border-l lg:border-t-0">
          <div className="mb-4 flex items-start justify-between gap-4">
            <div className="min-w-0">
              <h2 className="truncate font-mono text-sm text-zinc-200" title={record.filename}>
                {record.filename}
              </h2>
              <span
                className={`mt-1 inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  record.status === "FLAGGED"
                    ? "bg-amber-500/15 text-amber-300"
                    : record.status === "PASSED"
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "bg-zinc-700/40 text-zinc-300"
                }`}
              >
                {record.status}
              </span>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-200"
              aria-label="Close inspection"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <section className="mb-6">
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Technical
            </h3>
            <DetailRow
              label="Dimensions"
              value={
                record.width && record.height
                  ? `${record.width} × ${record.height}`
                  : "Unknown"
              }
            />
            <DetailRow
              label="Megapixels"
              value={record.megapixels != null ? `${record.megapixels} MP` : "—"}
            />
            <DetailRow label="File size" value={formatFileSize(record.file_size_bytes)} />
            <DetailRow
              label="Sharpness σ²"
              value={
                record.laplacian_variance != null
                  ? record.laplacian_variance.toFixed(2)
                  : "—"
              }
            />
          </section>

          <section className="mb-6">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Confidence Score
            </h3>
            {confidence != null ? (
              <div>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-zinc-400">Semantic QC</span>
                  <span className="font-semibold text-zinc-100">
                    {Math.round(confidence * 100)}%
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className={`h-full rounded-full ${
                      confidence >= 0.75 ? "bg-emerald-500" : "bg-amber-500"
                    }`}
                    style={{ width: `${Math.round(confidence * 100)}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-zinc-600">
                  Threshold for PASSED: 75%
                </p>
              </div>
            ) : (
              <p className="text-sm text-zinc-600">
                No semantic score recorded (audit may not have completed).
              </p>
            )}
          </section>

          <section className="mb-6">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Failure Reasons
            </h3>
            {record.ocr_text_detected && (
              <div className="mb-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200">
                <p className="mb-1 flex items-center gap-1 font-semibold">
                  <AlertTriangle className="h-3 w-3" />
                  OCR detected text
                </p>
                <p className="line-clamp-3 font-mono opacity-90">
                  {record.ocr_text_content || "(content unavailable)"}
                </p>
              </div>
            )}

            {flagList.length > 0 ? (
              <ul className="space-y-1.5">
                {flagList.map((flag, index) => (
                  <li
                    key={index}
                    className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200"
                  >
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                    <span>{flag}</span>
                  </li>
                ))}
              </ul>
            ) : (
              !record.ocr_text_detected && (
                <p className="flex items-center gap-1.5 text-sm text-emerald-300">
                  <CheckCircle2 className="h-4 w-4" />
                  No automated failures recorded.
                </p>
              )
            )}
          </section>

          <section className="mb-6">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Metadata
            </h3>
            <label className="mb-1 block text-xs text-zinc-500" htmlFor="modal-title">
              Title
            </label>
            <input
              id="modal-title"
              value={titleDraft}
              onChange={(event) => setTitleDraft(event.target.value)}
              placeholder="Generated on approval"
              className="mb-3 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:border-sky-500 focus:outline-none"
            />

            {record.generated_description && (
              <>
                <label className="mb-1 block text-xs text-zinc-500">Description</label>
                <textarea
                  readOnly
                  value={record.generated_description}
                  rows={3}
                  className="mb-3 w-full resize-none rounded-md border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-xs text-zinc-400"
                />
              </>
            )}

            {record.generated_keywords && record.generated_keywords.length > 0 && (
              <>
                <label className="mb-1 block text-xs text-zinc-500">
                  Keywords ({record.generated_keywords.length})
                </label>
                <div className="flex flex-wrap gap-1.5">
                  {record.generated_keywords.slice(0, 20).map((keyword, index) => (
                    <span
                      key={index}
                      className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-300"
                    >
                      {keyword}
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>

          <div className="mt-auto flex gap-3 pt-2">
            <button
              type="button"
              onClick={() =>
                onApprove?.(
                  record.id,
                  titleDraft ? { override_title: titleDraft } : undefined
                )
              }
              disabled={isApproving || record.status === "READY"}
              className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
            >
              {isApproving ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              {record.status === "READY" ? "Already Staged" : "Manual Override & Approve"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-700 px-4 py-2.5 text-sm font-medium text-zinc-300 transition-colors hover:border-zinc-500 hover:text-white"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
