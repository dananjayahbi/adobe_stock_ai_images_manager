"use client";

import ConfirmDialog from "@/components/ConfirmDialog";
import type { Prompt } from "@/lib/prompts";

export interface PromptDeleteDialogProps {
  /** The prompt pending deletion, or null when idle. */
  prompt: Prompt | null;
  isBusy?: boolean;
  /** Optional failure message from the last attempt. */
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Confirmation for deleting a prompt.
 *
 * A prompt is deleted in one click from its block, so this is the one place the
 * library still uses a dialog: the action is irreversible, and the wording has
 * to make clear that the *images are kept*. Without that, "delete" next to a
 * count of bound images reads like it will destroy them too.
 */
export function PromptDeleteDialog({
  prompt,
  isBusy = false,
  error = null,
  onConfirm,
  onCancel,
}: PromptDeleteDialogProps) {
  const bound = prompt?.bound_count ?? 0;

  return (
    <ConfirmDialog
      isOpen={prompt !== null}
      title="Delete this prompt?"
      message={
        `“${prompt?.title ?? ""}” will be removed from the library. ` +
        (bound > 0
          ? `Its ${bound} bound image${bound === 1 ? "" : "s"} will be kept and simply unbound — no image is deleted. `
          : "") +
        "This cannot be undone." +
        (error ? ` — Failed: ${error}` : "")
      }
      confirmLabel={isBusy ? "Deleting…" : "Delete prompt"}
      isBusy={isBusy}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}

export default PromptDeleteDialog;
