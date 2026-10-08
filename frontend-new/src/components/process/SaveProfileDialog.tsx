"use client";

import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";

interface SaveProfileDialogProps {
  open: boolean;
  onClose: () => void;
  onSave: (name: string) => Promise<void>;
  mediaType: string;
}

/** Name-and-save dialog for turning the current step set into a profile. */
export default function SaveProfileDialog({
  open,
  onClose,
  onSave,
  mediaType,
}: SaveProfileDialogProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName("");
      setError(null);
    }
  }, [open]);

  const submit = async () => {
    if (!name.trim()) {
      setError("Give the profile a name.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(name.trim());
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} width="max-w-md" labelledBy="save-profile-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps">Step profile</p>
        <h2 id="save-profile-title" className="mt-0.5 font-display text-xl text-ink-800">
          Save this recipe
        </h2>
      </div>
      <div className="px-6 py-5">
        <p className="mb-3 text-sm text-ink-400">
          Keep these steps and their settings for {mediaType} batches — they will
          be offered in the New Batch wizard.
        </p>
        <label htmlFor="profile-name" className="label-caps mb-1 block">
          Profile name
        </label>
        <input
          id="profile-name"
          type="text"
          value={name}
          autoFocus
          onChange={(event) => setName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") void submit();
          }}
          placeholder="e.g. Cut-outs, 4K"
          className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 placeholder:text-ink-400/70 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
        />
        {error && (
          <p className="mt-2 text-sm text-oxblood-500" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="flex justify-end gap-3 border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button onClick={() => void submit()} loading={saving}>
          Save profile
        </Button>
      </div>
    </Modal>
  );
}
