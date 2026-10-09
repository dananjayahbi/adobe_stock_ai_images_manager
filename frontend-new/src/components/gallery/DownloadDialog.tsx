"use client";

import { useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import { downloadSequentially, downloadZip } from "@/lib/downloads";

interface DownloadDialogProps {
  /** The selected records' ids. A single id downloads directly (no dialog). */
  recordIds: string[];
  open: boolean;
  onClose: () => void;
}

/**
 * Multi-download chooser: "one by one" vs "one ZIP".
 *
 * The single-image path never reaches this dialog — `downloadRecordFile`
 * fires directly — so this only opens for 2+ selections.
 */
export default function DownloadDialog({
  recordIds,
  open,
  onClose,
}: DownloadDialogProps) {
  const [busy, setBusy] = useState<null | "each" | "zip">(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (mode: "each" | "zip") => {
    setBusy(mode);
    setError(null);
    try {
      if (mode === "zip") await downloadZip(recordIds);
      else await downloadSequentially(recordIds);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} width="max-w-md" labelledBy="dl-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps">Download</p>
        <h2 id="dl-title" className="mt-0.5 font-display text-xl text-ink-800">
          {recordIds.length} images selected
        </h2>
      </div>

      <div className="space-y-3 px-6 py-5">
        <p className="text-sm text-ink-400">
          How would you like them downloaded?
        </p>

        <button
          type="button"
          onClick={() => void run("zip")}
          disabled={busy !== null}
          className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-4 py-3 text-left transition-colors hover:border-brass-400 hover:bg-parchment-200 disabled:opacity-60"
        >
          <p className="font-display text-base text-ink-800">
            One ZIP archive
          </p>
          <p className="mt-0.5 text-sm text-ink-400">
            A single <span className="font-stamp text-xs">gallery-images.zip</span>{" "}
            with every selected image.
          </p>
          {busy === "zip" && (
            <p className="mt-1 font-stamp text-[11px] uppercase tracking-wider text-brass-300">
              Building archive…
            </p>
          )}
        </button>

        <button
          type="button"
          onClick={() => void run("each")}
          disabled={busy !== null}
          className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-4 py-3 text-left transition-colors hover:border-brass-400 hover:bg-parchment-200 disabled:opacity-60"
        >
          <p className="font-display text-base text-ink-800">
            One by one
          </p>
          <p className="mt-0.5 text-sm text-ink-400">
            Downloads each image separately — your browser may ask permission
            for multiple downloads.
          </p>
          {busy === "each" && (
            <p className="mt-1 font-stamp text-[11px] uppercase tracking-wider text-brass-300">
              Downloading…
            </p>
          )}
        </button>

        {error && (
          <p className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="flex justify-end border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={busy !== null}>
          Cancel
        </Button>
      </div>
    </Modal>
  );
}
