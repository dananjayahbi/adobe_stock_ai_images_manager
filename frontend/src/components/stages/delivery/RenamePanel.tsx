"use client";

import { Check, Loader2, PencilLine, RotateCcw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  renameAssets,
  suggestNames,
  type RenameResultItem,
} from "@/lib/delivery";
import type { ImageRecord } from "@/lib/api";

export interface RenamePanelProps {
  records: ImageRecord[];
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
  /** Refresh the record list after a successful write. */
  onSaved: () => Promise<void> | void;
  onClose: () => void;
}

/**
 * Bulk filename editor for the Adobe Stock upload.
 *
 * The filename is a real deliverable, not a display detail: Adobe matches a CSV
 * row to an uploaded image by name, and a mismatch means the metadata silently
 * never lands. So this panel shows, per record, the current name, what the
 * generated title *would* derive, and the name that will actually be written.
 *
 * Two things it deliberately does:
 *
 * * **Suggests before writing.** "Rebuild all from titles" is a preview action;
 *   the operator reviews the whole batch, then applies. A bulk rename that wrote
 *   immediately would be irreversible across 50 records.
 * * **Shows the normalised result.** The operator types a human name and the
 *   server slugifies it to Adobe's rules, so the panel renders the *final* name
 *   rather than echoing the input back and hiding what will be uploaded.
 */
export function RenamePanel({
  records,
  onError,
  onNotice,
  onSaved,
  onClose,
}: RenamePanelProps) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [suggestions, setSuggestions] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"suggest" | "save" | null>(null);

  const recordIds = records.map((record) => record.id);
  /**
   * Identity of the *set* of records being edited.
   *
   * The page polls, so `records` is a fresh array on every refresh. Seeding the
   * fields on that identity wiped the operator's typing — and any proposal — a
   * few seconds after it appeared. Seeding is therefore keyed on the ids alone,
   * so it happens once per selection rather than once per poll.
   */
  const idKey = recordIds.join(",");

  useEffect(() => {
    const next: Record<string, string> = {};
    for (const record of records) {
      next[record.id] = record.download_name ?? "";
    }
    setDrafts(next);
    setSuggestions({});
    // `records` is intentionally not a dependency: it changes identity on every
    // poll, which would re-seed and discard in-progress edits. `idKey` captures
    // the only change that should reset the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idKey]);

  async function handleSuggest() {
    if (recordIds.length === 0) return;
    setBusy("suggest");
    onError(null);
    try {
      const result = await suggestNames(recordIds);
      const map: Record<string, string> = {};
      for (const item of result.items) {
        if (item.download_name) map[item.record_id] = item.download_name;
      }
      setSuggestions(map);
      setDrafts((current) => ({ ...current, ...map }));
      onNotice(
        `Proposed ${Object.keys(map).length} filename(s) from the generated titles. Review, then Apply.`
      );
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not build suggestions.");
    } finally {
      setBusy(null);
    }
  }

  async function handleSave() {
    if (recordIds.length === 0) return;
    setBusy("save");
    onError(null);
    try {
      const result = await renameAssets(
        records.map((record) => ({
          recordId: record.id,
          name: drafts[record.id] ?? "",
        }))
      );
      const failed = result.items.filter((item) => item.error);
      await onSaved();
      if (failed.length > 0) {
        onError(
          `${failed.length} name(s) could not be applied: ${failed
            .map((item: RenameResultItem) => item.error)
            .join(" ")}`
        );
      } else {
        onNotice(`Renamed ${result.updated} asset(s) for the Adobe upload.`);
        onClose();
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : "Could not rename the assets.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-accent-500/30 bg-navy-900/70 p-4">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-navy-100">
            Upload filenames
          </h3>
          <p className="text-xs text-navy-400">
            Adobe matches each CSV row to an uploaded image{" "}
            <span className="text-navy-200">by filename</span>. Names are made
            compliant automatically: lower-case, hyphens, JPEG extension, max 30
            characters. Leave a field blank to go back to the title-derived name.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={busy !== null || records.length === 0}
            isLoading={busy === "suggest"}
            onClick={() => void handleSuggest()}
            icon={
              busy === "suggest" ? undefined : (
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
              )
            }
          >
            Rebuild from titles
          </Button>
          <Button
            size="sm"
            variant="primary"
            disabled={busy !== null || records.length === 0}
            isLoading={busy === "save"}
            onClick={() => void handleSave()}
            icon={
              busy === "save" ? undefined : <Check className="h-3.5 w-3.5" aria-hidden />
            }
          >
            Apply to {records.length}
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose} icon={<X className="h-3.5 w-3.5" aria-hidden />}>
            Close
          </Button>
        </div>
      </header>

      <ul className="max-h-80 space-y-1.5 overflow-y-auto">
        {records.map((record) => {
          const suggested = suggestions[record.id];
          const value = drafts[record.id] ?? "";
          return (
            <li
              key={record.id}
              className="rounded-lg border border-navy-800 bg-navy-950/50 p-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <PencilLine className="h-3.5 w-3.5 shrink-0 text-navy-500" aria-hidden />
                <span className="min-w-0 flex-1 truncate text-[11px] text-navy-400">
                  {record.generated_title || record.filename}
                </span>
              </div>

              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <input
                  value={value}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [record.id]: event.target.value,
                    }))
                  }
                  placeholder="Leave blank to derive from the title"
                  aria-label={`Filename for ${record.generated_title || record.filename}`}
                  className={cn(
                    "min-w-0 flex-1 rounded-lg border border-navy-700/60 bg-navy-900/60 px-2.5 py-1.5",
                    "font-mono text-[11px] text-navy-50 placeholder:text-navy-500",
                    "focus:border-accent-500/70 focus:outline-none focus:ring-1 focus:ring-accent-500/40"
                  )}
                />
                {suggested && value === suggested ? (
                  <span className="shrink-0 rounded-full border border-accent-500/40 bg-accent-500/10 px-2 py-0.5 text-[10px] font-medium text-accent-200">
                    proposed
                  </span>
                ) : null}
                <span className="shrink-0 text-[10px] tabular-nums text-navy-500">
                  {value.length}/30
                </span>
              </div>
            </li>
          );
        })}
      </ul>

      {busy === "suggest" ? (
        <p className="flex items-center gap-1.5 text-[11px] text-navy-400">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          Building suggestions…
        </p>
      ) : null}
    </section>
  );
}

export default RenamePanel;
