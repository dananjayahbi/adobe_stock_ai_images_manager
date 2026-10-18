"use client";

import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import SlideConfirm from "@/components/ui/SlideConfirm";
import { deleteBatch } from "@/lib/batches";

interface DeleteBatchDialogProps {
  open: boolean;
  batchId: string;
  batchName: string;
  recordCount: number;
  onClose: () => void;
  /** Fired after the backend confirms the cascade delete. */
  onDeleted: () => void;
}

/**
 * Batch deletion confirmation, mirroring the gallery's record dialog: the
 * batch name and its image count are spelled out, and a slide-to-confirm
 * guards a DELETE that cascades to every record and file. A 409 (the batch
 * started running/queued since the button rendered) surfaces the backend's
 * `detail` verbatim inside the dialog instead of closing it.
 */
export default function DeleteBatchDialog({
  open,
  batchId,
  batchName,
  recordCount,
  onClose,
  onDeleted,
}: DeleteBatchDialogProps) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteBatch(batchId);
      onDeleted();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleting(false);
    }
  };

  const plural = recordCount !== 1;

  return (
    <Modal open={open} onClose={onClose} width="max-w-md" labelledBy="del-batch-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps text-oxblood-400">Permanent</p>
        <h2
          id="del-batch-title"
          className="mt-0.5 break-words font-display text-xl text-ink-800"
        >
          Delete “{batchName}”?
        </h2>
      </div>

      <div className="space-y-4 px-6 py-5">
        <p className="text-sm text-ink-400">
          This deletes the batch and its {recordCount} image
          {plural ? "s" : ""} — records and on-disk files are removed with it.
          There is no undo.
        </p>

        <SlideConfirm
          label={`Slide to delete ${recordCount} image${plural ? "s" : ""}`}
          tone="danger"
          disabled={deleting}
          onConfirm={() => void confirm()}
        />

        {error && (
          <p
            className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
            role="alert"
          >
            {error}
          </p>
        )}
      </div>

      <div className="flex justify-end border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={deleting}>
          Keep batch
        </Button>
      </div>
    </Modal>
  );
}
