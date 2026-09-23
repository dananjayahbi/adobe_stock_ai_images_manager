"use client";

import { AlertTriangle, CheckCircle2, ImageOff, Lock, Maximize2, Sparkles } from "lucide-react";
import { useState, type DragEvent } from "react";

import { formatFileSize, getPreviewUrl, getThumbnailUrl, type ImageRecord } from "@/lib/api";
import { cn } from "@/lib/cn";
import { isPromptDrag, readPromptDrag } from "@/lib/promptDrag";
import { formatScore, scoreTone, stageLabel } from "@/lib/stages";

const SCORE_TONES = {
  good: "border-emerald-500/40 bg-emerald-500/15 text-emerald-200",
  warn: "border-amber-500/40 bg-amber-500/15 text-amber-200",
  bad: "border-red-500/40 bg-red-500/15 text-red-200",
  none: "border-navy-700/60 bg-navy-800/70 text-navy-300",
};

export interface RecordCardProps {
  record: ImageRecord;
  isSelected: boolean;
  /** Dims the card and blocks interaction while a batch is running. */
  isRunning?: boolean;
  onToggleSelect: (id: string) => void;
  onInspect: (record: ImageRecord) => void;
  /**
   * Called when a prompt block is dropped onto this card.
   *
   * Optional: only the Collector binds prompts, so every other stage leaves
   * this undefined and the card stays a plain tile with no drop affordance.
   */
  onPromptDrop?: (recordId: string, promptId: string) => void;
  /** Title of the prompt bound to this image, shown as a badge. */
  promptTitle?: string | null;
  className?: string;
}

/**
 * One image tile.
 *
 * Selection is the card's primary interaction: the checkbox is always visible
 * (not hover-only) so a batch selection is readable without hovering every
 * tile, and the whole card is a button for keyboard users.
 *
 * When `onPromptDrop` is supplied the tile also becomes a drop target for a
 * dragged prompt block — the gesture that links a generation prompt to the
 * images it produced.
 */
export function RecordCard({
  record,
  isSelected,
  isRunning = false,
  onToggleSelect,
  onInspect,
  onPromptDrop,
  promptTitle = null,
  className,
}: RecordCardProps) {
  const [hasError, setHasError] = useState(false);
  const [isPromptOver, setPromptOver] = useState(false);
  const thumbnail = getThumbnailUrl(record);
  const fallback = getPreviewUrl(record.id, "working");
  const tone = scoreTone(record.acceptance_score);

  // Only intercept a drag that actually carries a prompt id. A file drop must
  // still fall through to whatever handles uploads, so the guard is on the
  // drag *type*, not merely on `onPromptDrop` being present.
  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (!onPromptDrop || !isPromptDrag(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "link";
    setPromptOver(true);
  }

  function handleDragLeave() {
    setPromptOver(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (!onPromptDrop || !isPromptDrag(event)) return;
    event.preventDefault();
    event.stopPropagation();
    setPromptOver(false);
    const promptId = readPromptDrag(event);
    if (promptId) onPromptDrop(record.id, promptId);
  }

  return (
    <div
      onDragOver={onPromptDrop ? handleDragOver : undefined}
      onDragLeave={onPromptDrop ? handleDragLeave : undefined}
      onDrop={onPromptDrop ? handleDrop : undefined}
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-navy-850/50 transition-colors duration-150 ease-swift",
        isSelected
          ? "border-accent-500/70 shadow-glow-sm"
          : "border-navy-700/50 hover:border-navy-600",
        isPromptOver && "border-accent-400 bg-accent-500/10 shadow-glow",
        isRunning && "opacity-60",
        className
      )}
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-navy-950">
        {!hasError ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={thumbnail ?? fallback}
            alt={record.filename}
            loading="lazy"
            onError={() => setHasError(true)}
            className="h-full w-full object-cover transition-transform duration-300 ease-swift group-hover:scale-[1.03]"
          />
        ) : (
          <div className="grid h-full w-full place-items-center text-navy-600">
            <ImageOff className="h-6 w-6" aria-hidden />
          </div>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-navy-950/90 to-transparent" />

        {isPromptOver ? (
          <div className="pointer-events-none absolute inset-0 grid place-items-center bg-navy-950/70">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-accent-400/60 bg-accent-500/20 px-3 py-1 text-[11px] font-semibold text-accent-100">
              <Sparkles className="h-3 w-3" aria-hidden />
              Bind prompt
            </span>
          </div>
        ) : null}

        {/* Selection toggle — always visible so batch state is never hidden. */}
        <button
          type="button"
          onClick={() => onToggleSelect(record.id)}
          aria-pressed={isSelected}
          aria-label={isSelected ? `Deselect ${record.filename}` : `Select ${record.filename}`}
          className={cn(
            "absolute left-2 top-2 grid h-6 w-6 place-items-center rounded-md border transition-colors",
            isSelected
              ? "border-accent-400 bg-accent-500 text-navy-950"
              : "border-white/25 bg-navy-950/60 text-transparent hover:border-accent-400/70"
          )}
        >
          <CheckCircle2 className="h-4 w-4" aria-hidden />
        </button>

        {/* Score badge. */}
        <span
          className={cn(
            "absolute right-2 top-2 rounded-md border px-1.5 py-0.5 text-[10px] font-semibold tabular-nums backdrop-blur",
            SCORE_TONES[tone]
          )}
        >
          {formatScore(record.acceptance_score)}
        </span>

        {/* Inspect affordance. */}
        <button
          type="button"
          onClick={() => onInspect(record)}
          aria-label={`Inspect ${record.filename}`}
          className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-lg border border-white/20 bg-navy-950/70 text-navy-100 opacity-0 backdrop-blur transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        >
          <Maximize2 className="h-3.5 w-3.5" aria-hidden />
        </button>

        {record.queued_stage ? (
          <span className="absolute bottom-2 left-2 inline-flex items-center gap-1 rounded-full border border-accent-500/40 bg-accent-500/20 px-2 py-0.5 text-[10px] font-semibold text-accent-100 backdrop-blur">
            <Lock className="h-3 w-3" aria-hidden />
            Queued
          </span>
        ) : null}

        {promptTitle ? (
          <span
            className="absolute bottom-2 right-2 inline-flex max-w-[70%] items-center gap-1 rounded-full border border-violet-400/40 bg-violet-500/20 px-2 py-0.5 text-[10px] font-semibold text-violet-100 backdrop-blur"
            title={`Prompt: ${promptTitle}`}
          >
            <Sparkles className="h-3 w-3 shrink-0" aria-hidden />
            <span className="truncate">{promptTitle}</span>
          </span>
        ) : null}
      </div>

      <div className="space-y-1.5 p-2.5">
        <p className="truncate font-mono text-[11px] text-navy-200" title={record.filename}>
          {record.filename}
        </p>
        <div className="flex items-center justify-between gap-2 text-[10px] text-navy-400">
          <span className="truncate">{stageLabel(record.stage)}</span>
          <span className="shrink-0 tabular-nums">
            {formatFileSize(record.file_size_bytes)}
          </span>
        </div>
        {record.ocr_text_detected ? (
          <p className="inline-flex items-center gap-1 text-[10px] font-medium text-red-300">
            <AlertTriangle className="h-3 w-3" aria-hidden />
            Text detected
          </p>
        ) : null}
      </div>
    </div>
  );
}

export default RecordCard;
