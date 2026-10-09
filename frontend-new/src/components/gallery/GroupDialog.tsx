"use client";

import { useEffect, useState } from "react";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import {
  assignRecords,
  createGroup,
  deleteGroup,
  fetchGroups,
} from "@/lib/groups";
import type { GalleryGroup } from "@/lib/types";

interface GroupDialogProps {
  recordIds: string[];
  open: boolean;
  onClose: () => void;
  onChanged: () => void;
  /** Pre-selected folder when moving into an existing one. */
  mode?: "create" | "add";
}

/**
 * Group the selected images into a folder: create a new one, or drop them
 * into an existing folder. Deleting a folder is offered here too — it only
 * releases the images back to the top level, never deletes them.
 */
export default function GroupDialog({
  recordIds,
  open,
  onClose,
  onChanged,
  mode = "create",
}: GroupDialogProps) {
  const [name, setName] = useState("");
  const [groups, setGroups] = useState<GalleryGroup[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName("");
    setError(null);
    fetchGroups()
      .then(setGroups)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [open]);

  const submit = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} width="max-w-lg" labelledBy="grp-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps">Organise</p>
        <h2 id="grp-title" className="mt-0.5 font-display text-xl text-ink-800">
          Group {recordIds.length} image{recordIds.length !== 1 ? "s" : ""}
        </h2>
      </div>

      <div className="space-y-5 px-6 py-5">
        {mode === "create" && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void submit(() => createGroup(name, recordIds));
            }}
            className="space-y-2"
          >
            <label htmlFor="grp-name" className="label-caps">
              New folder
            </label>
            <div className="flex gap-2">
              <input
                id="grp-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Botanical set"
                maxLength={200}
                className="flex-1 rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 placeholder:text-ink-400/70 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
              />
              <Button
                type="submit"
                size="sm"
                disabled={busy || !name.trim()}
                loading={busy}
              >
                Create
              </Button>
            </div>
          </form>
        )}

        <div className="space-y-2">
          <p className="label-caps">Existing folders</p>
          {groups.length === 0 && (
            <p className="text-sm text-ink-400">
              No folders yet — create one above.
            </p>
          )}
          <ul className="space-y-1.5">
            {groups.map((group) => (
              <li
                key={group.id}
                className="flex items-center justify-between gap-3 rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink-800">{group.name}</p>
                  <p className="font-stamp text-[10px] uppercase tracking-wider text-ink-400">
                    {group.image_count} image{group.image_count !== 1 ? "s" : ""}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() =>
                      void submit(() => assignRecords(recordIds, group.id))
                    }
                  >
                    Add here
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={() => void submit(() => deleteGroup(group.id))}
                    title="Remove the folder (images go back to the top level)"
                  >
                    ✕
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {error && (
          <p className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="flex justify-end border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" size="sm" onClick={onClose} disabled={busy}>
          Close
        </Button>
      </div>
    </Modal>
  );
}
