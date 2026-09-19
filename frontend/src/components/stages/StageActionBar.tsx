"use client";

import { Clock, Play, Sparkles } from "lucide-react";
import { useState } from "react";

import type { PipelineStage, StageKey } from "@/lib/stages";

interface StageActionBarProps {
  stage: PipelineStage;
  selectedCount: number;
  eligibleCount: number;
  visibleCount: number;
  isBusy: boolean;
  /** Delay between LLM calls for Stage 6. */
  delaySeconds: number;
  onDelayChange: (seconds: number) => void;
  onRun: () => void;
  onSelectAll: () => void;
  onClearSelection: () => void;
  /** Stage 6 only: preview/download the CSV. */
  onPreviewCsv?: () => void;
  onDownloadCsv?: () => void;
}

/** The stage key whose action this stage's bar triggers. */
const STAGE_ACTION: Partial<Record<PipelineStage, StageKey>> = {
  COLLECTED: "ocr",
  OCR_CLEAR: "upscale",
  UPSCALED: "refine",
  REFINED: "compatibility",
  COMPATIBLE: "metadata",
  METADATA_READY: "gallery",
};

const ACTION_LABELS: Record<StageKey, string> = {
  ocr: "Scan for text",
  upscale: "Upscale images",
  refine: "Auto-refine",
  compatibility: "Run compatibility check",
  metadata: "Generate metadata",
  gallery: "Publish to gallery",
};

const ACTION_HINTS: Record<StageKey, string> = {
  ocr: "Images containing text are removed from the pipeline.",
  upscale: "Raises resolution toward the 15-25 MP Adobe Stock target.",
  refine: "Applies corrections until the acceptance score clears 80%.",
  compatibility: "Full acceptance algorithm; images under 80% are flagged.",
  metadata: "Calls the model once per image, with a pause to avoid rate limits.",
  gallery: "Copies the file, embeds metadata, and stages it for upload.",
};

export default function StageActionBar({
  stage,
  selectedCount,
  eligibleCount,
  visibleCount,
  isBusy,
  delaySeconds,
  onDelayChange,
  onRun,
  onSelectAll,
  onClearSelection,
  onPreviewCsv,
  onDownloadCsv,
}: StageActionBarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const actionKey = STAGE_ACTION[stage];

  // Terminal stages have no forward action; the operator can only review.
  if (!actionKey) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-4 py-3">
        <p className="text-sm text-zinc-400">
          {stage === "OCR_REJECTED"
            ? "These images contain embedded text and are excluded from the pipeline. Inspect one to confirm, then delete it."
            : "These images could not reach the 80% acceptance threshold. Inspect one for the specific remediation steps."}
        </p>
      </div>
    );
  }

  const runnableCount = selectedCount > 0 ? selectedCount : eligibleCount;
  const isMetadataStage = actionKey === "metadata";

  return (
    <div className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onSelectAll}
            disabled={visibleCount === 0}
            className="rounded-md border border-zinc-700 bg-zinc-800/70 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Select all ({visibleCount})
          </button>

          <button
            type="button"
            onClick={onClearSelection}
            disabled={selectedCount === 0}
            className="rounded-md border border-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Clear
          </button>

          {isMetadataStage && (
            <>
              <button
                type="button"
                onClick={onPreviewCsv}
                disabled={visibleCount === 0}
                className="rounded-md border border-zinc-700 bg-zinc-800/70 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Preview CSV
              </button>
              <button
                type="button"
                onClick={onDownloadCsv}
                disabled={visibleCount === 0}
                className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 transition-colors hover:bg-emerald-500/20 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Download CSV
              </button>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isMetadataStage && (
            <button
              type="button"
              onClick={() => setShowAdvanced((value) => !value)}
              aria-expanded={showAdvanced}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-zinc-500 transition-colors hover:text-zinc-300"
            >
              <Clock className="h-3.5 w-3.5" />
              Delay
            </button>
          )}

          <button
            type="button"
            onClick={onRun}
            disabled={isBusy || runnableCount === 0}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
          >
            <Play className="h-4 w-4" />
            {isBusy
              ? "Running…"
              : `${ACTION_LABELS[actionKey]} (${runnableCount})`}
          </button>
        </div>
      </div>

      <p className="text-xs text-zinc-500">
        {ACTION_HINTS[actionKey]}
        {selectedCount > 0
          ? ` ${selectedCount} selected.`
          : ` No selection - all ${eligibleCount} eligible image(s) will run.`}
      </p>

      {isMetadataStage && showAdvanced && (
        <label className="flex items-center gap-3 border-t border-zinc-800 pt-3 text-xs text-zinc-400">
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-fuchsia-400" />
            Pause between API calls
          </span>
          <input
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={delaySeconds}
            onChange={(event) => onDelayChange(Number(event.target.value))}
            className="h-1 flex-1 accent-sky-500"
            aria-label="Delay between metadata API calls"
          />
          <span className="w-14 text-right tabular-nums text-zinc-300">
            {delaySeconds.toFixed(1)}s
          </span>
        </label>
      )}
    </div>
  );
}
