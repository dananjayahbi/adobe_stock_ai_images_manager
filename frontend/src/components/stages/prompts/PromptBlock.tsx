"use client";

import { Check, GripVertical, ImageIcon, Pencil, Trash2 } from "lucide-react";
import type { DragEvent } from "react";

import { cn } from "@/lib/cn";
import { writePromptDrag } from "@/lib/promptDrag";
import type { Prompt } from "@/lib/prompts";

export interface PromptBlockProps {
  prompt: Prompt;
  /** Highlighted as the current drop target for a selection. */
  isActive?: boolean;
  isBusy?: boolean;
  /** Selected images currently on the collection side, for the bind button. */
  selectedCount: number;
  onEdit: (prompt: Prompt) => void;
  onDelete: (prompt: Prompt) => void;
  onBindSelection: (prompt: Prompt) => void;
  onToggleUsed: (prompt: Prompt) => void;
  onSelect: (prompt: Prompt) => void;
}

/**
 * One prompt in the library, rendered as a draggable block.
 *
 * Dragging is the primary binding gesture: the operator picks a prompt up here
 * and drops it on the image(s) it produced. The whole card is draggable rather
 * than a small handle, because the gesture is used constantly and a 12px target
 * would be a constant miss — the grip icon is an affordance, not the target.
 *
 * The explicit "Bind N" button exists because dragging is unavailable to
 * keyboard and touch users; both paths call the same handler.
 */
export function PromptBlock({
  prompt,
  isActive = false,
  isBusy = false,
  selectedCount,
  onEdit,
  onDelete,
  onBindSelection,
  onToggleUsed,
  onSelect,
}: PromptBlockProps) {
  const isUsed = prompt.bound_count > 0 || prompt.status === "USED";
  const isArchived = prompt.status === "ARCHIVED";

  function handleDragStart(event: DragEvent<HTMLDivElement>) {
    writePromptDrag(event.dataTransfer, prompt.id);
    onSelect(prompt);
  }

  return (
    <div
      draggable={!isBusy}
      onDragStart={handleDragStart}
      onClick={() => onSelect(prompt)}
      className={cn(
        "group relative cursor-grab rounded-xl border bg-navy-850/60 p-3 transition-colors duration-150 ease-swift",
        isActive
          ? "border-accent-500/70 shadow-glow-sm"
          : "border-navy-700/50 hover:border-navy-600",
        isArchived && "opacity-60",
        isBusy && "cursor-wait opacity-70"
      )}
    >
      <div className="flex items-start gap-2">
        <GripVertical
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-navy-500 group-hover:text-navy-300"
          aria-hidden
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p
              className="truncate text-xs font-semibold text-navy-50"
              title={prompt.title}
            >
              {prompt.title || "Untitled prompt"}
            </p>
            {isUsed ? (
              <span
                className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-200"
                title="Used — bound to at least one image"
              >
                <Check className="h-2.5 w-2.5" aria-hidden />
                Used
              </span>
            ) : (
              <span className="shrink-0 rounded-full border border-navy-600/60 bg-navy-800/70 px-1.5 py-0.5 text-[10px] font-semibold text-navy-300">
                Unused
              </span>
            )}
          </div>

          <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[11px] leading-relaxed text-navy-300">
            {prompt.body}
          </p>

          {prompt.negative_prompt ? (
            <p className="mt-1 line-clamp-2 text-[10px] italic leading-relaxed text-navy-500">
              Negative: {prompt.negative_prompt}
            </p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium tabular-nums",
                prompt.bound_count > 0
                  ? "bg-accent-500/15 text-accent-200"
                  : "bg-navy-800/70 text-navy-400"
              )}
            >
              <ImageIcon className="h-2.5 w-2.5" aria-hidden />
              {prompt.bound_count} image{prompt.bound_count === 1 ? "" : "s"}
            </span>

            {(prompt.tags ?? []).slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="rounded-md bg-navy-800/70 px-1.5 py-0.5 text-[10px] text-navy-300"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Actions are always visible on touch, hover-revealed on pointer devices
          so a long library stays scannable. */}
      <div className="mt-2 flex flex-wrap items-center gap-1.5 border-t border-navy-700/40 pt-2 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
        <button
          type="button"
          disabled={isBusy || selectedCount === 0}
          onClick={(event) => {
            event.stopPropagation();
            onBindSelection(prompt);
          }}
          className="inline-flex items-center gap-1 rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1 text-[10px] font-medium text-accent-200 transition-colors hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:border-navy-700/60 disabled:bg-navy-800/60 disabled:text-navy-500"
          title={
            selectedCount === 0
              ? "Select images on the left, or drag this block onto an image"
              : `Bind the ${selectedCount} selected image(s) to this prompt`
          }
        >
          <ImageIcon className="h-2.5 w-2.5" aria-hidden />
          Bind {selectedCount > 0 ? selectedCount : ""}
        </button>

        <button
          type="button"
          disabled={isBusy}
          onClick={(event) => {
            event.stopPropagation();
            onToggleUsed(prompt);
          }}
          className="inline-flex items-center gap-1 rounded-md border border-navy-700/60 bg-navy-800/60 px-2 py-1 text-[10px] font-medium text-navy-200 transition-colors hover:bg-navy-750 disabled:opacity-50"
        >
          <Check className="h-2.5 w-2.5" aria-hidden />
          {isUsed ? "Mark unused" : "Mark used"}
        </button>

        <button
          type="button"
          disabled={isBusy}
          onClick={(event) => {
            event.stopPropagation();
            onEdit(prompt);
          }}
          aria-label={`Edit ${prompt.title}`}
          className="inline-flex items-center gap-1 rounded-md border border-navy-700/60 bg-navy-800/60 px-2 py-1 text-[10px] font-medium text-navy-200 transition-colors hover:bg-navy-750 disabled:opacity-50"
        >
          <Pencil className="h-2.5 w-2.5" aria-hidden />
          Edit
        </button>

        <button
          type="button"
          disabled={isBusy}
          onClick={(event) => {
            event.stopPropagation();
            onDelete(prompt);
          }}
          aria-label={`Delete ${prompt.title}`}
          className="ml-auto inline-flex items-center gap-1 rounded-md border border-red-500/30 bg-red-500/10 px-2 py-1 text-[10px] font-medium text-red-200 transition-colors hover:bg-red-500/20 disabled:opacity-50"
        >
          <Trash2 className="h-2.5 w-2.5" aria-hidden />
        </button>
      </div>
    </div>
  );
}

export default PromptBlock;
