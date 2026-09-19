"use client";

/**
 * The standard "Delete" action for a stage page's selection bar.
 *
 * Deletion is the one irreversible operation in the pipeline and the operator
 * reaches it from every stage, so the confirmation is mandatory rather than
 * optional — the backend unlinks the inbox original, the thumbnail, and every
 * staged copy (refined, upscaled, ready-to-upload). The dialog names that
 * consequence instead of asking a bare "delete?".
 *
 * Owning this in one component is what keeps the seven stage pages consistent;
 * a page supplies only the ids and the delete call.
 */

import { Trash2 } from "lucide-react";

import ConfirmDialog from "@/components/ConfirmDialog";
import { Button } from "@/components/ui/Button";
import { pluralise, useConfirmAction } from "@/hooks/useConfirmAction";

interface StageDeleteButtonProps {
  /** Ids currently selected on the page. */
  recordIds: string[];
  /** Filenames matching `recordIds`, used to name a single-record delete. */
  filenames?: string[];
  disabled?: boolean;
  /** Performs the deletion; rejecting keeps the dialog open with the error. */
  onDelete: (ids: string[]) => Promise<void>;
}

export default function StageDeleteButton({
  recordIds,
  filenames = [],
  disabled = false,
  onDelete,
}: StageDeleteButtonProps) {
  const confirm = useConfirmAction<string[]>();
  const count = recordIds.length;
  const isSingle = count === 1;

  const subject = isSingle
    ? filenames[0] || `record ${recordIds[0]?.slice(0, 8)}`
    : pluralise(count, "image");

  return (
    <>
      <Button
        size="sm"
        variant="danger"
        disabled={disabled || count === 0}
        onClick={() => confirm.request(recordIds)}
        icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
      >
        Delete{count > 1 ? ` (${count})` : ""}
      </Button>

      <ConfirmDialog
        isOpen={confirm.isOpen}
        title={isSingle ? "Delete this image?" : `Delete ${count} images?`}
        message={
          `This permanently removes ${subject} from project storage, including ` +
          "the original upload, the thumbnail, and any refined, upscaled, or " +
          "ready-to-upload copies. This cannot be undone." +
          (confirm.error ? ` — Failed: ${confirm.error}` : "")
        }
        confirmLabel={confirm.isBusy ? "Deleting…" : "Delete permanently"}
        isBusy={confirm.isBusy}
        onConfirm={() => void confirm.run(onDelete)}
        onCancel={confirm.cancel}
      />
    </>
  );
}
