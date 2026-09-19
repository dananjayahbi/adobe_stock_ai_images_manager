"use client";

/**
 * Delete control usable from any stage.
 *
 * Deletion is the one irreversible action in the pipeline, and the operator
 * reaches it from every stage (a rejected OCR image, a failed compatibility
 * check, a duplicate that slipped through). The backend removes the inbox
 * original, the thumbnail, and every staged copy - refined, upscaled, and the
 * ready-to-upload file - so the confirmation names that consequence rather than
 * saying "delete?" and hoping.
 */

import { Trash2 } from "lucide-react";
import { useState } from "react";

import ConfirmDialog from "@/components/ConfirmDialog";

interface DeleteRecordsButtonProps {
  /** Ids to delete. One id renders a single-record label. */
  recordIds: string[];
  /** Filenames for the confirmation message; falls back to the id count. */
  filenames?: string[];
  disabled?: boolean;
  /** Called after the server confirms; the caller refreshes its list. */
  onDeleted: (deletedIds: string[]) => void;
  onDelete: (ids: string[]) => Promise<void>;
  /** Compact icon-only rendering for dense toolbars. */
  variant?: "button" | "icon";
  label?: string;
}

export default function DeleteRecordsButton({
  recordIds,
  filenames = [],
  disabled = false,
  onDeleted,
  onDelete,
  variant = "button",
  label,
}: DeleteRecordsButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const count = recordIds.length;
  const isSingle = count === 1;

  const handleConfirm = async () => {
    setIsBusy(true);
    setError(null);
    try {
      await onDelete(recordIds);
      setIsOpen(false);
      onDeleted(recordIds);
    } catch (err) {
      // Keep the dialog open so the failure is visible next to the action that
      // caused it, rather than in a toast the operator may miss.
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setIsBusy(false);
    }
  };

  const subject = isSingle
    ? filenames[0] || recordIds[0].slice(0, 8)
    : `${count} images`;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        disabled={disabled || count === 0}
        aria-label={label ?? (isSingle ? "Delete image" : `Delete ${count} images`)}
        className={
          variant === "icon"
            ? "rounded-md p-1.5 text-navy-400 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
            : "inline-flex items-center gap-1.5 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40"
        }
      >
        <Trash2 className="h-3.5 w-3.5" />
        {variant === "button" &&
          (label ?? (isSingle ? "Delete" : `Delete (${count})`))}
      </button>

      <ConfirmDialog
        isOpen={isOpen}
        title={isSingle ? "Delete this image?" : `Delete ${count} images?`}
        message={
          `This permanently removes ${subject} from the project storage, ` +
          "including the original upload, the thumbnail, and any refined, " +
          "upscaled, or ready-to-upload copies. This cannot be undone." +
          (error ? ` — Failed: ${error}` : "")
        }
        confirmLabel={isBusy ? "Deleting…" : "Delete permanently"}
        isBusy={isBusy}
        onConfirm={handleConfirm}
        onCancel={() => {
          setIsOpen(false);
          setError(null);
        }}
      />
    </>
  );
}
