"use client";

import { Check, Loader2, ScanText, SlidersHorizontal } from "lucide-react";

import { getPreviewUrl, getThumbnailUrl, type ImageRecord } from "@/lib/api";
import {
  STAGE_COLORS,
  formatScore,
  isTerminalStage,
  scoreTone,
  stageLabel,
} from "@/lib/stages";

interface StageCardProps {
  record: ImageRecord;
  isSelected: boolean;
  isRunning: boolean;
  onToggleSelect: (id: string) => void;
  onInspect: (record: ImageRecord) => void;
}

const TONE_STYLES: Record<ReturnType<typeof scoreTone>, string> = {
  good: "bg-emerald-500/20 text-emerald-200 border-emerald-500/40",
  warn: "bg-amber-500/20 text-amber-200 border-amber-500/40",
  bad: "bg-red-500/20 text-red-200 border-red-500/40",
  none: "bg-zinc-700/50 text-zinc-400 border-zinc-600/50",
};

/**
 * One image tile in a stage grid.
 *
 * Shows the *working* preview rather than the thumbnail, so the operator sees
 * the actual pixels the pipeline produced (upscaled/refined), not the original
 * upload that may no longer be relevant.
 */
export default function StageCard({
  record,
  isSelected,
  isRunning,
  onToggleSelect,
  onInspect,
}: StageCardProps) {
  const score = record.acceptance_score;
  const tone = scoreTone(score);
  const detail = record.stage_details;

  // A single contextual line beats a wall of metrics at grid density.
  let hint = "";
  if (detail?.ocr?.reason && record.stage.startsWith("OCR")) {
    hint = detail.ocr.reason;
  } else if (detail?.upscale?.backend && record.stage === "UPSCALED") {
    hint = `${detail.upscale.output_megapixels.toFixed(1)} MP · ${detail.upscale.backend}`;
  } else if (detail?.refine && record.stage === "REFINED") {
    hint = `${formatScore(detail.refine.initial_score)} → ${formatScore(detail.refine.final_score)}`;
  } else if (detail?.compatibility?.summary) {
    hint = detail.compatibility.summary;
  } else if (record.generated_title) {
    hint = record.generated_title;
  }

  return (
    <div
      className={`group relative overflow-hidden rounded-xl border transition-colors ${
        isSelected
          ? "border-sky-500 bg-sky-500/10"
          : "border-zinc-800 bg-zinc-900/50 hover:border-zinc-700"
      }`}
    >
      <button
        type="button"
        onClick={() => onInspect(record)}
        className="block w-full text-left"
        aria-label={`Inspect ${record.filename}`}
      >
        <div className="relative aspect-[4/3] overflow-hidden bg-zinc-950">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={getPreviewUrl(record.id, "working", record.updated_at)}
            alt={record.filename}
            loading="lazy"
            className="h-full w-full object-contain"
            // The working file may not exist yet (pre-Stage-3); fall back to
            // the generated thumbnail so the tile is never blank.
            onError={(event) => {
              const thumb = getThumbnailUrl(record);
              if (thumb && event.currentTarget.src !== thumb) {
                event.currentTarget.src = thumb;
              }
            }}
          />

          <span
            className={`absolute left-2 top-2 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold tabular-nums backdrop-blur ${TONE_STYLES[tone]}`}
          >
            {formatScore(score)}
          </span>

          {isRunning && (
            <span className="absolute inset-0 grid place-items-center bg-zinc-950/70">
              <Loader2 className="h-6 w-6 animate-spin text-sky-400" />
            </span>
          )}
        </div>
      </button>

      <div className="space-y-1.5 p-2.5">
        <div className="flex items-center justify-between gap-2">
          <span
            className={`truncate rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${STAGE_COLORS[record.stage]}`}
          >
            {stageLabel(record.stage)}
          </span>

          <button
            type="button"
            onClick={() => onToggleSelect(record.id)}
            aria-pressed={isSelected}
            aria-label={isSelected ? "Deselect image" : "Select image"}
            className={`grid h-5 w-5 shrink-0 place-items-center rounded border transition-colors ${
              isSelected
                ? "border-sky-400 bg-sky-500 text-white"
                : "border-zinc-600 bg-zinc-800/80 text-transparent hover:border-zinc-500"
            }`}
          >
            <Check className="h-3 w-3" />
          </button>
        </div>

        <p className="truncate text-xs font-medium text-zinc-300" title={record.filename}>
          {record.filename}
        </p>

        {hint && (
          <p className="line-clamp-2 text-[11px] leading-snug text-zinc-500" title={hint}>
            {hint}
          </p>
        )}

        {record.refine_passes > 0 && (
          <p className="flex items-center gap-1 text-[10px] text-violet-400/80">
            <SlidersHorizontal className="h-3 w-3" />
            {record.refine_passes} refine pass{record.refine_passes === 1 ? "" : "es"}
          </p>
        )}

        {record.ocr_text_detected && isTerminalStage(record.stage) && (
          <p className="flex items-center gap-1 text-[10px] text-amber-400/90">
            <ScanText className="h-3 w-3" />
            Text detected
          </p>
        )}
      </div>
    </div>
  );
}
