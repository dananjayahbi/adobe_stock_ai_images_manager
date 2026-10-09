"use client";

import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import SlideConfirm from "@/components/ui/SlideConfirm";
import { deleteRecords } from "@/lib/records";

interface DeleteDialogProps {
  recordIds: string[];
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}

/**
 * Delete confirmation, gated behind a slide-to-confirm so a stray click can
 * never destroy images. Handles one record or many — the copy adapts.
 */
export default function DeleteDialog({
  recordIds,
  open,
  onClose,
  onDeleted,
}: DeleteDialogProps) {
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  const count = recordIds.length;
  const plural = count !== 1;

  const confirm = async () => {
    setDeleting(true);
    setError(null);
    try {
      await deleteRecords(recordIds);
      onDeleted();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} width="max-w-md" labelledBy="del-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps text-oxblood-400">Permanent</p>
        <h2 id="del-title" className="mt-0.5 font-display text-xl text-ink-800">
          Delete {count} image{plural ? "s" : ""}?
        </h2>
      </div>

      <div className="space-y-4 px-6 py-5">
        <p className="text-sm text-ink-400">
          This removes {plural ? "these images" : "this image"} and every
          on-disk artifact {plural ? "they own" : "it owns"} — working copy,
          thumbnail, staged file. There is no undo.
        </p>

        <SlideConfirm
          label={`Slide to delete ${count} image${plural ? "s" : ""}`}
          tone="danger"
          disabled={deleting}
          onConfirm={() => void confirm()}
        />

        {error && (
          <p className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="flex justify-end border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={deleting}>
          Keep {plural ? "them" : "it"}
        </Button>
      </div>
    </Modal>
  );
}
