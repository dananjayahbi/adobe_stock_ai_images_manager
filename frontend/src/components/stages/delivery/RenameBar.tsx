"use client";

import { Sparkles, Tags } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { applySuggestedNames } from "@/lib/delivery";
import type { ImageRecord } from "@/lib/api";

export interface RenameBarProps {
  /** The records currently selected on the page. */
  records: ImageRecord[];
  onError?: (message: string | null) => void;
  onNotice?: (message: string | null) => void;
  /** Refresh the list after a write, so the new names show immediately. */
  onApplied?: () => Promise<void> | void;
  /** Open the manual editor. Omitted when the host page has no editor. */
  onEdit?: () => void;
  disabled?: boolean;
  className?: string;
}

/**
 * One-click naming for a selection, shared by every delivery stage.
 *
 * Naming used to be reachable only through the manual editor, which meant
 * "rename them all" was really "rename them all by hand". The model already
 * chose a name for each asset while looking at it, so this surfaces that
 * decision directly:
 *
 * * **Use suggested names** applies the model's proposals. It writes
 *   immediately — applying a proposal that was stored at generation time is a
 *   deliberate single decision, and there is nothing to review that the
 *   operator cannot see in the list afterwards.
 * * **Filenames** opens the editor, for the cases where the operator wants to
 *   review or type a name by hand.
 *
 * The count of records that actually have a proposal is shown, because the
 * button must not imply every selected asset has one: a record generated before
 * the model was asked to name assets falls back to its title, and saying so is
 * better than letting the operator discover it.
 */
export function RenameBar({
  records,
  onError,
  onNotice,
  onApplied,
  onEdit,
  disabled = false,
  className,
}: RenameBarProps) {
  const [busy, setBusy] = useState(false);

  const count = records.length;
  const proposed = records.filter((record) =>
    Boolean(record.suggested_filename)
  ).length;
  // A proposal that is already the record's delivered name means applying again
  // would change nothing — worth knowing before clicking.
  const pending = records.filter(
    (record) =>
      Boolean(record.suggested_filename) &&
      record.suggested_filename !== record.download_name
  ).length;

  async function handleApply() {
    if (count === 0) return;
    setBusy(true);
    onError?.(null);
    try {
      const result = await applySuggestedNames(records.map((record) => record.id));
      await onApplied?.();
      const fallbacks = count - proposed;
      const parts = [`Applied names to ${result.updated} asset(s).`];
      if (fallbacks > 0) {
        parts.push(
          `${fallbacks} had no model suggestion and kept a title-derived name.`
        );
      }
      onNotice?.(parts.join(" "));
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Could not apply the names.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <Button
        size="sm"
        variant="secondary"
        disabled={disabled || busy || count === 0}
        isLoading={busy}
        onClick={() => void handleApply()}
        icon={busy ? undefined : <Sparkles className="h-3.5 w-3.5" aria-hidden />}
        title={
          count === 0
            ? "Select images to name them"
            : `Apply the metadata model's suggested filenames to ${count} asset(s)` +
              (pending > 0 ? ` — ${pending} would change` : " — nothing would change")
        }
      >
        Use suggested names{count > 0 ? ` (${count})` : ""}
      </Button>

      {onEdit ? (
        <Button
          size="sm"
          variant="secondary"
          disabled={disabled || busy || count === 0}
          onClick={onEdit}
          icon={<Tags className="h-3.5 w-3.5" aria-hidden />}
          title="Review or type the upload filenames Adobe will match against the CSV"
        >
          Filenames{count > 0 ? ` (${count})` : ""}
        </Button>
      ) : null}
    </div>
  );
}

export default RenameBar;
