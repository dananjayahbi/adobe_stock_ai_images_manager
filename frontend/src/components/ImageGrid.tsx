"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ImageOff,
  Loader2,
  ScanSearch,
} from "lucide-react";
import { useState } from "react";

import { getThumbnailUrl, type ImageRecord, type ImageStatus } from "@/lib/api";

interface ImageGridProps {
  records: ImageRecord[];
  onInspect?: (record: ImageRecord) => void;
  onApprove?: (id: string) => void;
  isLoading?: boolean;
}

type FilterKey = "ALL" | ImageStatus;

const BORDER_BY_STATUS: Record<ImageStatus, string> = {
  PENDING: "border-zinc-700",
  AUDITING: "border-zinc-500 animate-pulse",
  PASSED: "border-emerald-500",
  FLAGGED: "border-amber-500",
  APPROVED: "border-violet-500",
  READY: "border-blue-500",
};

const FILTERS: FilterKey[] = [
  "ALL",
  "PENDING",
  "AUDITING",
  "PASSED",
  "FLAGGED",
  "READY",
];

function flagsToList(
  flags: ImageRecord["semantic_flags"]
): string[] {
  if (!flags) return [];
  if (Array.isArray(flags)) return flags.map(String);
  return Object.entries(flags).map(([key, value]) => `${key}: ${String(value)}`);
}

export default function ImageGrid({
  records,
  onInspect,
  onApprove,
  isLoading = false,
}: ImageGridProps) {
  const [activeFilter, setActiveFilter] = useState<FilterKey>("ALL");
  const [failedImages, setFailedImages] = useState<Record<string, boolean>>({});

  const visible =
    activeFilter === "ALL"
      ? records
      : records.filter((record) => record.status === activeFilter);

  const countFor = (key: FilterKey) =>
    key === "ALL"
      ? records.length
      : records.filter((record) => record.status === key).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((key) => {
          const isActive = activeFilter === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setActiveFilter(key)}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors ${
                isActive
                  ? "border-sky-500 bg-sky-500/15 text-sky-300"
                  : "border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
              }`}
            >
              {key === "ALL" ? "All" : key.charAt(0) + key.slice(1).toLowerCase()}
              <span className="ml-1.5 opacity-70">{countFor(key)}</span>
            </button>
          );
        })}
      </div>

      {isLoading && records.length === 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <div
              key={index}
              className="h-64 animate-pulse rounded-xl border border-zinc-800 bg-zinc-900/60"
            />
          ))}
        </div>
      ) : visible.length === 0 ? (
        <p className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-zinc-500">
          No images to display for this filter.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {visible.map((record) => {
            const thumbUrl = getThumbnailUrl(record);
            const showImage = thumbUrl && !failedImages[record.id];
            const confidence = record.semantic_confidence_score;
            const flagList = flagsToList(record.semantic_flags);
            const canApprove = record.status === "PASSED" || record.status === "FLAGGED";

            return (
              <article
                key={record.id}
                className={`flex flex-col overflow-hidden rounded-xl border-2 bg-zinc-900/70 ${BORDER_BY_STATUS[record.status]}`}
              >
                <button
                  type="button"
                  onClick={() => onInspect?.(record)}
                  className="group relative block aspect-square w-full overflow-hidden bg-zinc-950"
                  aria-label={`Inspect ${record.filename}`}
                >
                  {showImage ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={thumbUrl}
                      alt={record.filename}
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform group-hover:scale-105"
                      onError={() =>
                        setFailedImages((prev) => ({ ...prev, [record.id]: true }))
                      }
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <ImageOff className="h-10 w-10 text-zinc-700" />
                    </div>
                  )}

                  {confidence !== null && confidence !== undefined && (
                    <span
                      className={`absolute right-2 top-2 rounded-full px-2 py-0.5 text-xs font-semibold backdrop-blur ${
                        confidence >= 0.75
                          ? "bg-emerald-500/85 text-emerald-950"
                          : "bg-amber-500/85 text-amber-950"
                      }`}
                    >
                      {Math.round(confidence * 100)}%
                    </span>
                  )}

                  {record.status === "AUDITING" && (
                    <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded-full bg-zinc-950/80 px-2 py-0.5 text-xs text-zinc-300">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Auditing
                    </span>
                  )}
                </button>

                <div className="flex flex-1 flex-col gap-2 p-3">
                  <p className="truncate font-mono text-xs text-zinc-300" title={record.filename}>
                    {record.filename}
                  </p>

                  <p className="text-xs text-zinc-500">
                    {record.megapixels != null ? `${record.megapixels} MP` : "— MP"}
                    {record.laplacian_variance != null
                      ? ` · σ² ${record.laplacian_variance.toFixed(1)}`
                      : ""}
                  </p>

                  {record.status === "FLAGGED" && flagList.length > 0 && (
                    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2">
                      <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-amber-300">
                        <AlertTriangle className="h-3 w-3" />
                        Flagged
                      </p>
                      <ul className="list-disc space-y-0.5 pl-4 text-xs text-amber-200/90">
                        {flagList.slice(0, 3).map((flag, index) => (
                          <li key={index}>{flag}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {record.status === "FLAGGED" && flagList.length === 0 && (
                    <p className="text-xs text-amber-300/90">
                      Failed automated QC thresholds.
                    </p>
                  )}

                  <div className="mt-auto pt-1">
                    {canApprove ? (
                      <button
                        type="button"
                        onClick={() => onApprove?.(record.id)}
                        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
                      >
                        <ScanSearch className="h-3.5 w-3.5" />
                        Approve &amp; Tag
                      </button>
                    ) : record.status === "READY" ? (
                      <p className="flex items-center justify-center gap-1.5 rounded-md border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-xs font-medium text-blue-300">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Staged for upload
                      </p>
                    ) : (
                      <p className="text-center text-xs text-zinc-600">
                        {record.status === "APPROVED" ? "Processing…" : "Awaiting audit"}
                      </p>
                    )}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
