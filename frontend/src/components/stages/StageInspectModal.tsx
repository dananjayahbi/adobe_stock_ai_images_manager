"use client";

import { Loader2, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { getPreviewUrl, resetStage, type ImageRecord } from "@/lib/api";
import { STAGE_COLORS, formatScore, stageLabel } from "@/lib/stages";

import AcceptanceReportPanel from "./AcceptanceReportPanel";
import StageDetailList from "./StageDetailList";

interface StageInspectModalProps {
  record: ImageRecord | null;
  isOpen: boolean;
  isBusy: boolean;
  onClose: () => void;
  onReset: (record: ImageRecord) => void;
  /** Bumped after a stage run so previews bypass the browser cache. */
  previewVersion?: string | number;
}

type PreviewVariant = "working" | "original" | "refined";

/**
 * Full-size inspection of one record.
 *
 * The side-by-side original/current view is the point of this modal: the
 * operator has to judge whether an automatic refinement actually helped, and
 * that cannot be done from a thumbnail.
 */
export default function StageInspectModal({
  record,
  isOpen,
  isBusy,
  onClose,
  onReset,
  previewVersion,
}: StageInspectModalProps) {
  const [variant, setVariant] = useState<PreviewVariant>("working");
  const [isResetting, setIsResetting] = useState(false);

  // Reset the variant when a different record opens.
  useEffect(() => {
    setVariant("working");
  }, [record?.id]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [isOpen, onClose]);

  if (!isOpen || !record) return null;

  const report = record.acceptance_report;
  const remediation = record.stage_details?.compatibility?.remediation;

  const handleReset = async () => {
    setIsResetting(true);
    try {
      const updated = await resetStage(record.id);
      onReset(updated);
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-zinc-950/85 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={`Inspect ${record.filename}`}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="my-6 w-full max-w-6xl rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 px-5 py-3.5">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-zinc-100">
              {record.filename}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
              <span
                className={`rounded border px-1.5 py-0.5 font-medium ${STAGE_COLORS[record.stage]}`}
              >
                {stageLabel(record.stage)}
              </span>
              <span>{formatScore(record.acceptance_score)} acceptance</span>
              {record.megapixels && <span>{record.megapixels.toFixed(1)} MP</span>}
              {record.refine_passes > 0 && (
                <span>{record.refine_passes} refine pass(es)</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => void handleReset()}
              disabled={isResetting || isBusy || record.stage === "PUBLISHED"}
              title={
                record.stage === "PUBLISHED"
                  ? "Published assets cannot be reset."
                  : "Return this image to Stage 1 to reprocess it."
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {isResetting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RotateCcw className="h-3.5 w-3.5" />
              )}
              Reset to Stage 1
            </button>

            <button
              type="button"
              onClick={onClose}
              aria-label="Close inspection"
              className="rounded p-1.5 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
          {/* Preview with variant switcher */}
          <div className="space-y-3">
            <div className="flex gap-1 rounded-lg border border-zinc-800 bg-zinc-950/50 p-1">
              {(
                [
                  ["original", "Original"],
                  ["working", "Current"],
                  ["refined", "Refined"],
                ] as [PreviewVariant, string][]
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setVariant(value)}
                  aria-pressed={variant === value}
                  className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                    variant === value
                      ? "bg-zinc-800 text-zinc-100"
                      : "text-zinc-500 hover:text-zinc-300"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="grid max-h-[70vh] place-items-center overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={`${variant}-${previewVersion ?? ""}`}
                src={getPreviewUrl(record.id, variant, previewVersion)}
                alt={`${record.filename} (${variant})`}
                className="max-h-[66vh] w-auto max-w-full object-contain"
              />
            </div>
          </div>

          {/* Analysis */}
          <div className="max-h-[76vh] space-y-5 overflow-y-auto pr-1">
            <StageDetailList record={record} />

            {report ? (
              <AcceptanceReportPanel report={report} remediation={remediation} />
            ) : (
              <p className="rounded-lg border border-dashed border-zinc-800 px-4 py-6 text-center text-sm text-zinc-500">
                No acceptance report yet. Run Stage 4 or Stage 5 to score this
                image.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
