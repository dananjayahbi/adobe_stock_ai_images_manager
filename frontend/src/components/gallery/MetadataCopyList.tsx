"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";
import type { ImageRecord } from "@/lib/api";

export interface MetadataCopyListProps {
  record: ImageRecord;
}

/** The fields Adobe takes from a CSV row, in the order the portal shows them. */
function fields(record: ImageRecord): { label: string; value: string }[] {
  const keywords = record.generated_keywords ?? [];
  return [
    {
      label: "Upload filename",
      // The name Adobe will match this asset by, and the exact value the CSV's
      // Filename column carries. Shown first because it is the field that makes
      // the metadata land or silently not land. It is NOT `record.filename` —
      // that is the original upload's name, which never matches the CSV.
      value: record.upload_filename ?? record.download_name ?? record.filename,
    },
    {
      label: "Suggested filename",
      // What the metadata model proposed while looking at the image. Shown as a
      // separate field, never merged into the one above, so it is always clear
      // which name is actually being delivered and which is only a proposal.
      value: record.suggested_filename ?? "",
    },
    { label: "Title", value: record.generated_title ?? "" },
    { label: "Description", value: record.generated_description ?? "" },
    { label: "Keywords", value: keywords.join(", ") },
  ];
}

/**
 * Per-field copy controls for one asset's metadata.
 *
 * The bulk CSV export covers the normal path, but the operator regularly needs
 * one field for one image — pasting a title into the portal by hand, checking a
 * keyword list, or fixing a single row Adobe rejected. Rebuilding a whole CSV to
 * copy one title is disproportionate, so each field gets its own button.
 *
 * A failure is reported distinctly rather than silently: a denied clipboard is
 * otherwise indistinguishable from a successful copy, and the operator would
 * paste stale text without knowing.
 */
export function MetadataCopyList({ record }: MetadataCopyListProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);

  async function handleCopy(label: string, value: string) {
    const ok = await copyText(value);
    if (ok) {
      setFailed(null);
      setCopied(label);
      setTimeout(() => setCopied((current) => (current === label ? null : current)), 1500);
    } else {
      setCopied(null);
      setFailed(label);
      setTimeout(() => setFailed((current) => (current === label ? null : current)), 2500);
    }
  }

  const rows = fields(record);

  return (
    <div className="space-y-2">
      <p className="text-[11px] uppercase tracking-wide text-navy-400">
        Metadata — copy one by one
      </p>

      <ul className="space-y-1.5">
        {rows.map(({ label, value }) => {
          const isEmpty = !value;
          const state = copied === label ? "copied" : failed === label ? "failed" : "idle";

          return (
            <li
              key={label}
              className="flex items-start gap-2 rounded-lg border border-navy-800 bg-navy-950/50 px-2.5 py-2"
            >
              <div className="min-w-0 flex-1">
                <p className="text-[10px] uppercase tracking-wide text-navy-500">
                  {label}
                </p>
                <p
                  className={cn(
                    "mt-0.5 whitespace-pre-wrap break-words text-[11px] leading-relaxed",
                    isEmpty ? "italic text-navy-600" : "text-navy-200"
                  )}
                >
                  {isEmpty ? "Not generated yet" : value}
                </p>
              </div>

              <button
                type="button"
                disabled={isEmpty}
                onClick={() => void handleCopy(label, value)}
                aria-label={`Copy ${label.toLowerCase()}`}
                title={
                  isEmpty
                    ? `No ${label.toLowerCase()} to copy`
                    : state === "copied"
                      ? "Copied"
                      : state === "failed"
                        ? "Clipboard blocked — select the text and copy manually"
                        : `Copy ${label.toLowerCase()}`
                }
                className={cn(
                  "inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition-colors",
                  "disabled:cursor-not-allowed disabled:opacity-40",
                  state === "copied" &&
                    "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
                  state === "failed" && "border-red-500/50 bg-red-500/15 text-red-300",
                  state === "idle" &&
                    "border-navy-700 text-navy-300 hover:border-accent-500/50 hover:text-accent-200"
                )}
              >
                {state === "copied" ? (
                  <Check className="h-3 w-3" aria-hidden />
                ) : (
                  <Copy className="h-3 w-3" aria-hidden />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default MetadataCopyList;
