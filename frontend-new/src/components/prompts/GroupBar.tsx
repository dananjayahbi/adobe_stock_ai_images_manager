"use client";

/**
 * Batch-grouping controls: the group filter chips and the selection action bar.
 *
 * Two jobs in one strip because they share a subject (folders):
 *
 * - **Chips** — every folder with its count, rendered from the server's
 *   `groups` so the chip list can never drift from the rows. Clicking filters
 *   the library to that folder; clicking the active chip clears the filter.
 * - **Selection bar** — appears when one or more prompts are ticked. Names a
 *   folder once and moves the whole selection in a single round trip (the
 *   "I use these prompts like a batch" flow), or clears their folders.
 */
import { FolderInput, FolderX, X } from "lucide-react";
import { useState } from "react";

import Button from "@/components/ui/Button";
import type { PromptGroup } from "@/lib/prompts";

interface GroupBarProps {
  /** Server-derived folders (name + count). */
  groups: PromptGroup[];
  /** Committed folder filter ("" = everything). */
  activeGroup: string;
  onGroupFilter: (name: string) => void;
  /** Ids currently ticked. The bar renders only when non-empty. */
  selectedCount: number;
  onClearSelection: () => void;
  /** Move the selection into `name` ("" ungroups). */
  onGroupSelection: (name: string) => Promise<void>;
  isBusy: boolean;
}

export default function GroupBar({
  groups,
  activeGroup,
  onGroupFilter,
  selectedCount,
  onClearSelection,
  onGroupSelection,
  isBusy,
}: GroupBarProps) {
  const [folderName, setFolderName] = useState("");

  const move = () => {
    const name = folderName.trim();
    if (!name) return;
    void onGroupSelection(name);
    setFolderName("");
  };

  const ungroup = () => {
    void onGroupSelection("");
  };

  return (
    <div className="space-y-3">
      {/* Folder chips — server counts, active chip highlighted. */}
      {groups.length > 0 && (
        <div
          role="group"
          aria-label="Folder filters"
          className="flex flex-wrap items-center gap-1.5"
        >
          <span className="label-caps mr-1 text-ink-400">Folders</span>
          {groups.map((entry) => (
            <button
              key={entry.name}
              type="button"
              aria-pressed={activeGroup === entry.name}
              onClick={() =>
                onGroupFilter(activeGroup === entry.name ? "" : entry.name)
              }
              title={
                activeGroup === entry.name
                  ? "Clear this folder filter"
                  : `Show only “${entry.name}”`
              }
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm border px-2.5 py-1 font-stamp text-[11px] uppercase tracking-[0.14em] transition-colors ${
                activeGroup === entry.name
                  ? "border-oxblood-500 bg-oxblood-500/10 text-oxblood-400"
                  : "border-parchment-500 text-ink-600 hover:border-brass-400 hover:text-ink-800"
              }`}
            >
              {entry.name}
              <span className="tabular-nums opacity-70">{entry.count}</span>
            </button>
          ))}
          {activeGroup && (
            <button
              type="button"
              onClick={() => onGroupFilter("")}
              className="inline-flex items-center gap-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 hover:text-oxblood-400"
            >
              <X className="h-3 w-3" aria-hidden /> Clear
            </button>
          )}
        </div>
      )}

      {/* Selection bar — only while a batch is ticked. */}
      {selectedCount > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-sm border border-brass-400/60 bg-brass-400/10 px-3 py-2">
          <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-700">
            {selectedCount} selected
          </span>

          <label htmlFor="group-folder-name" className="sr-only">
            Folder name
          </label>
          <input
            id="group-folder-name"
            type="text"
            list="existing-prompt-folders"
            value={folderName}
            maxLength={120}
            disabled={isBusy}
            placeholder="Folder name…"
            onChange={(event) => setFolderName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") move();
            }}
            className="w-52 rounded-sm border border-parchment-500 bg-parchment-50 px-2.5 py-1.5 text-sm text-ink-800 placeholder:text-ink-400 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60"
          />
          <datalist id="existing-prompt-folders">
            {groups.map((entry) => (
              <option key={entry.name} value={entry.name} />
            ))}
          </datalist>

          <Button
            size="sm"
            type="button"
            loading={isBusy}
            disabled={!folderName.trim()}
            onClick={move}
            title="Move the selected prompts into this folder"
          >
            <FolderInput className="h-3 w-3" aria-hidden /> Move to folder
          </Button>
          <Button
            size="sm"
            variant="ghost"
            type="button"
            loading={isBusy}
            onClick={ungroup}
            title="Remove the selected prompts from any folder"
          >
            <FolderX className="h-3 w-3" aria-hidden /> Ungroup
          </Button>
          <button
            type="button"
            onClick={onClearSelection}
            className="ml-auto inline-flex items-center gap-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 hover:text-oxblood-400"
          >
            <X className="h-3 w-3" aria-hidden /> Deselect
          </button>
        </div>
      )}
    </div>
  );
}
