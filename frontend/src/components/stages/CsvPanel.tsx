"use client";

import { AlertTriangle, Check, Copy, Download, Loader2, X } from "lucide-react";
import { useState } from "react";

import { downloadCsv, previewCsv } from "@/lib/api";
import type { CsvPreview } from "@/lib/stages";

interface CsvPanelProps {
  /** When set, only these records are exported; otherwise every ready row is. */
  recordIds?: string[];
  onClose: () => void;
}

/**
 * Adobe Stock CSV preview and download.
 *
 * Adobe matches CSV rows to uploaded files by filename, so showing the exact
 * document before download is the cheapest way to catch a mismatch. Warnings
 * (truncated titles, trimmed keywords) are surfaced rather than silently
 * applied.
 */
export default function CsvPanel({ recordIds, onClose }: CsvPanelProps) {
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = async () => {
    setIsLoading(true);
    setError(null);
    try {
      setPreview(await previewCsv(recordIds));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build the CSV.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = async () => {
    try {
      await downloadCsv(recordIds);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed.");
    }
  };

  const handleCopy = async () => {
    if (!preview) return;
    try {
      await navigator.clipboard.writeText(preview.csv_text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Clipboard access was denied.");
    }
  };

  return (
    <section className="space-y-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">
            Adobe Stock CSV
          </h3>
          <p className="text-xs text-zinc-500">
            Columns: Filename, Title, Keywords, Category, Releases. Upload it
            alongside the images; Adobe matches rows by filename.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-800/70 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700 disabled:opacity-50"
          >
            {isLoading && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {preview ? "Refresh" : "Build preview"}
          </button>

          {preview && (
            <>
              <button
                type="button"
                onClick={() => void handleCopy()}
                className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 bg-zinc-800/70 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700"
              >
                {copied ? (
                  <Check className="h-3.5 w-3.5 text-emerald-400" />
                ) : (
                  <Copy className="h-3.5 w-3.5" />
                )}
                {copied ? "Copied" : "Copy"}
              </button>

              <button
                type="button"
                onClick={() => void handleDownload()}
                className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-500"
              >
                <Download className="h-3.5 w-3.5" />
                Download
              </button>
            </>
          )}

          <button
            type="button"
            onClick={onClose}
            aria-label="Close CSV panel"
            className="rounded p-1 text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {error && (
        <p className="rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-200">
          {error}
        </p>
      )}

      {preview?.warnings && preview.warnings.length > 0 && (
        <ul className="space-y-1">
          {preview.warnings.slice(0, 5).map((warning, index) => (
            <li
              key={index}
              className="flex items-start gap-1.5 rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-200"
            >
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
              {warning}
            </li>
          ))}
          {preview.warnings.length > 5 && (
            <li className="text-xs text-zinc-500">
              …and {preview.warnings.length - 5} more.
            </li>
          )}
        </ul>
      )}

      {preview && (
        <>
          <p className="text-xs text-zinc-500">
            {preview.row_count} data row(s)
            {preview.skipped.length > 0 &&
              ` · ${preview.skipped.length} skipped`}
          </p>
          <pre className="max-h-72 overflow-auto rounded-lg border border-zinc-800 bg-zinc-950/70 p-3 text-[11px] leading-relaxed text-zinc-300">
            {preview.csv_text}
          </pre>
        </>
      )}

      {!preview && !isLoading && !error && (
        <p className="rounded-lg border border-dashed border-zinc-800 px-4 py-6 text-center text-xs text-zinc-500">
          Build a preview to check the rows before uploading to Adobe.
        </p>
      )}
    </section>
  );
}
