"use client";

import { Check, GripVertical, ImageIcon, Pencil, Trash2 } from "lucide-react";
import type { DragEvent } from "react";

import PromptCopyButton from "@/components/stages/prompts/PromptCopyButton";
import PromptStateBadges from "@/components/stages/prompts/PromptStateBadges";
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
  // The two axes are read from their own fields and never derived from each
  // other. `isUsed` is the *status* (consumed); `isBound` is the *binding*
  // count. A prompt can be used and unbound at the same time.
  const isUsed = prompt.status === "USED";
  const isBound = prompt.bound_count > 0;
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
            <div className="flex shrink-0 items-center gap-1.5">
              {/* The copy control sits beside the title so it is reachable
                  without hovering the action row — copying is the most
                  frequent action on a prompt block. */}
              <PromptCopyButton
                value={prompt.body}
                label={`Copy prompt text for ${prompt.title}`}
                suffix={
                  prompt.negative_prompt
                    ? `Negative prompt: ${prompt.negative_prompt}`
                    : null
                }
                isBusy={isBusy}
              />
              <PromptStateBadges prompt={prompt} />
            </div>
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
                isBound
                  ? "bg-accent-500/15 text-accent-200"
                  : "bg-navy-800/70 text-navy-400"
              )}
              title={
                isBound
                  ? `${prompt.bound_count} image(s) bound to this prompt`
                  : "No image bound to this prompt"
              }
            >
              <ImageIcon className="h-2.5 w-2.5" aria-hidden />
              {prompt.bound_count} bound
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
          // A bound prompt is used by definition (the backend enforces it), so
          // the toggle would be a no-op. Disabling it with the reason beats a
          // button that appears to work and silently changes nothing.
          disabled={isBusy || isBound}
          onClick={(event) => {
            event.stopPropagation();
            onToggleUsed(prompt);
          }}
          title={
            isBound
              ? `Bound to ${prompt.bound_count} image(s), so it stays used. Unbind first.`
              : isUsed
                ? "Mark this prompt as unused (back to draft)"
                : "Mark this prompt as used"
          }
          className="inline-flex items-center gap-1 rounded-md border border-navy-700/60 bg-navy-800/60 px-2 py-1 text-[10px] font-medium text-navy-200 transition-colors hover:bg-navy-750 disabled:cursor-not-allowed disabled:opacity-50"
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
