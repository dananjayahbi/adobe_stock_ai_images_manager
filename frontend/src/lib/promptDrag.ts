/**
 * Drag-and-drop contract for binding a prompt to images.
 *
 * The prompt sidebar and the collection grid are separate component trees, so
 * the drag payload is the only thing they share. Keeping the MIME type and the
 * encode/decode pair in one module means a rename cannot half-land: both the
 * drag source and the drop target import from here.
 *
 * `text/plain` is set alongside the custom type because some browsers (and the
 * HTML5 drag preview) only surface standard types. Reading falls back to it, so
 * a drag that loses the custom type still binds instead of silently doing
 * nothing.
 */

import type { DragEvent as ReactDragEvent } from "react";

/** Custom MIME type carrying the dragged prompt id. */
export const PROMPT_DRAG_TYPE = "application/x-adobe-prompt-id";

/**
 * Stamped on the drop target so the drop effect can be distinguished from a
 * file drop (the collection grid also accepts dropped image files).
 */
export const PROMPT_DRAG_LABEL = "adobe-prompt";

/** True when the drag event carries a prompt rather than files. */
export function isPromptDrag(event: ReactDragEvent | DragEvent): boolean {
  const types = Array.from(event.dataTransfer?.types ?? []);
  return types.includes(PROMPT_DRAG_TYPE) || types.includes(PROMPT_DRAG_LABEL);
}

/** Write a prompt id into a drag event's data transfer. */
export function writePromptDrag(
  dataTransfer: DataTransfer,
  promptId: string
): void {
  dataTransfer.setData(PROMPT_DRAG_TYPE, promptId);
  dataTransfer.setData(PROMPT_DRAG_LABEL, promptId);
  dataTransfer.setData("text/plain", promptId);
  dataTransfer.effectAllowed = "link";
}

/** Read a prompt id from a drag event, or null when the drag is not a prompt. */
export function readPromptDrag(event: ReactDragEvent): string | null {
  const data = event.dataTransfer;
  if (!data) return null;
  const value =
    data.getData(PROMPT_DRAG_TYPE) ||
    data.getData(PROMPT_DRAG_LABEL) ||
    data.getData("text/plain");
  return value ? value.trim() || null : null;
}
