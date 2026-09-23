"use client";

import { Download, FileSpreadsheet, Package, Table2 } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  downloadSelectionBundle,
  downloadSelectionCsv,
  previewSelectionCsv,
  type DeliverySelection,
} from "@/lib/delivery";

export interface CsvExportActionsProps {
  /** Records currently selected on the page. */
  selectedIds: string[];
  /**
   * Whether the export may include records whose metadata is not ready yet.
   *
   * The Gallery exports *published* assets, which the server's default
   * "ready-only" filter would exclude — so it must pass `false`. See
   * `lib/delivery.ts` for why the flag exists rather than a second endpoint.
   */
  onlyReady?: boolean;
  /** Rendered inline (a toolbar) or as a panel with the preview attached. */
  variant?: "toolbar" | "panel";
  /**
   * Whether to offer the "ZIP + CSV" action at all.
   *
   * A bundle holds the *staged* files, and only some stages have them, so a page
   * whose records are not staged must not offer the control: clicking it can only
   * produce a 409. Withheld rather than disabled-with-no-reason, because
   * `bundleHint` then says which action produces a stageable file.
   */
  includeBundle?: boolean;
  /** Shown in place of the bundle button when `includeBundle` is false. */
  bundleHint?: string;
  onError?: (message: string | null) => void;
  onNotice?: (message: string | null) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * The CSV/ZIP delivery actions, shared by every stage from Metadata onward.
 *
 * Both actions are **selection-driven**: the operator selects images and
 * generates exactly that CSV, or bundles exactly those images with their CSV.
 * "Export everything" was the previous behaviour and it is the wrong default —
 * an operator uploads a chosen batch, and a CSV listing images that are not in
 * the upload is worse than no CSV.
 *
 * This component owns no page state: it reports outcomes through the callbacks
 * so the hosting page keeps its single existing message banner.
 */
export function CsvExportActions({
  selectedIds,
  onlyReady = true,
  variant = "toolbar",
  includeBundle = true,
  bundleHint,
  onError,
  onNotice,
  disabled = false,
  className,
}: CsvExportActionsProps) {
  const [busy, setBusy] = useState<"csv" | "zip" | null>(null);
  const [preview, setPreview] = useState<{
    csv_text: string;
    row_count: number;
    warnings: string[];
  } | null>(null);

  const count = selectedIds.length;
  const selection: DeliverySelection = { recordIds: selectedIds, onlyReady };

  async function run(kind: "csv" | "zip") {
    if (count === 0) {
      onError?.("Select at least one image first.");
      return;
    }
    setBusy(kind);
    onError?.(null);
    try {
      if (kind === "csv") {
        await downloadSelectionCsv(selection);
        onNotice?.(`CSV generated for ${count} image(s).`);
      } else {
        await downloadSelectionBundle(selection);
        onNotice?.(`ZIP with ${count} image(s) and their CSV downloaded.`);
      }
    } catch (err) {
      onError?.(describe(err, kind));
    } finally {
      setBusy(null);
    }
  }

  async function handlePreview() {
    if (count === 0) {
      onError?.("Select at least one image first.");
      return;
    }
    setBusy("csv");
    onError?.(null);
    try {
      setPreview(await previewSelectionCsv(selection));
    } catch (err) {
      onError?.(describe(err, "csv"));
    } finally {
      setBusy(null);
    }
  }

  const buttons = (
    <>
      <Button
        size="sm"
        variant="secondary"
        disabled={disabled || busy !== null || count === 0}
        isLoading={busy === "csv"}
        onClick={() => void handlePreview()}
        icon={busy === "csv" ? undefined : <Table2 className="h-3.5 w-3.5" aria-hidden />}
        title={
          count === 0
            ? "Select images to preview their CSV rows"
            : `Preview the ${count} CSV row(s) before downloading`
        }
      >
        Preview CSV
      </Button>

      <Button
        size="sm"
        variant="secondary"
        disabled={disabled || busy !== null || count === 0}
        onClick={() => void run("csv")}
        icon={<FileSpreadsheet className="h-3.5 w-3.5" aria-hidden />}
        title={
          count === 0
            ? "Select images to generate their CSV"
            : `Generate and download the CSV for ${count} selected image(s)`
        }
      >
        CSV {count > 0 ? `(${count})` : ""}
      </Button>

      {includeBundle ? (
        <Button
          size="sm"
          variant="secondary"
          disabled={disabled || busy !== null || count === 0}
          onClick={() => void run("zip")}
          icon={<Package className="h-3.5 w-3.5" aria-hidden />}
          title={
            count === 0
              ? "Select images to bundle them"
              : `Download a ZIP of the ${count} image(s) plus their CSV`
          }
        >
          ZIP + CSV {count > 0 ? `(${count})` : ""}
        </Button>
      ) : null}
    </>
  );

  /**
   * What replaces the bundle button when the bundle cannot work here.
   *
   * Silence would be worse than a disabled button: the operator would think the
   * feature was removed. This says what is missing and how to get it.
   */
  const bundleNotice = !includeBundle && bundleHint ? (
    <span
      className="max-w-md text-[11px] leading-snug text-navy-400"
      title={bundleHint}
    >
      {bundleHint}
    </span>
  ) : null;

  /**
   * The preview block, rendered in BOTH variants.
   *
   * This was originally only in the panel variant, so on the Gallery the
   * "Preview CSV" button fetched the rows and then displayed nothing at all —
   * the button looked broken. A control must never be able to succeed silently.
   */
  const previewBlock = preview ? (
    <div className="w-full space-y-2">
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-navy-400">
        <span className="text-navy-200">
          {preview.row_count} row{preview.row_count === 1 ? "" : "s"}
        </span>
        {preview.warnings.length > 0 ? (
          <span className="text-amber-300">
            {preview.warnings.length} warning
            {preview.warnings.length === 1 ? "" : "s"}
          </span>
        ) : null}
        <button
          type="button"
          onClick={() => setPreview(null)}
          className="ml-auto text-navy-400 underline-offset-2 hover:text-navy-100 hover:underline"
        >
          Hide
        </button>
      </div>

      {preview.warnings.length > 0 ? (
        <ul className="max-h-24 space-y-0.5 overflow-y-auto rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-[11px] text-amber-200">
          {preview.warnings.slice(0, 8).map((warning) => (
            <li key={warning}>• {warning}</li>
          ))}
        </ul>
      ) : null}

      <pre className="max-h-72 overflow-auto rounded-lg border border-navy-800 bg-navy-950/80 p-3 text-[11px] leading-relaxed text-navy-200">
        {preview.csv_text}
      </pre>
    </div>
  ) : null;

  if (variant === "toolbar") {
    return (
      <div className={cn("flex flex-wrap items-center gap-2", className)}>
        {buttons}
        {bundleNotice}
        {previewBlock}
      </div>
    );
  }

  return (
    <section
      className={cn(
        "space-y-3 rounded-xl border border-navy-800 bg-navy-900/60 p-4",
        className
      )}
    >
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-navy-100">
            Adobe Stock delivery
          </h3>
          <p className="text-xs text-navy-400">
            Select images above, then generate their CSV or a ZIP containing the
            images <em>and</em> the CSV. Adobe matches rows to files by filename,
            so the bundle keeps the two in step.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">{buttons}</div>
      </header>

      {bundleNotice}
      {previewBlock}
    </section>
  );
}

/** Turn an axios/blob error into something an operator can act on. */
function describe(err: unknown, kind: "csv" | "zip"): string {
  const label = kind === "csv" ? "CSV" : "ZIP";
  if (err instanceof Error) {
    // A blob response hides the server's JSON detail, so axios reports a
    // generic parse failure; say what it most likely means instead.
    if (/blob|json|parse/i.test(err.message)) {
      return `Could not build the ${label}. Check that the selected images have generated metadata.`;
    }
    return err.message;
  }
  return `Could not build the ${label}.`;
}

export default CsvExportActions;
