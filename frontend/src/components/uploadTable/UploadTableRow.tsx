"use client";

import { Download, ImageOff } from "lucide-react";

import CopyButton from "@/components/CopyButton";
import type { UploadTableItem } from "@/lib/api";

interface UploadTableRowProps {
  item: UploadTableItem;
  index: number;
}

/** One row: image preview + copyable title, description, and keywords. */
export default function UploadTableRow({ item, index }: UploadTableRowProps) {
  const keywordCount = item.keywords.length;

  return (
    <article className="grid gap-4 rounded-xl border border-navy-800 bg-navy-900/50 p-4 md:grid-cols-[10rem_1fr]">
      {/* Preview + download */}
      <div className="flex flex-col gap-2">
        <div className="overflow-hidden rounded-lg border border-navy-800 bg-navy-950">
          {item.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.thumbnail_url}
              alt={item.title || item.filename}
              loading="lazy"
              className="block h-32 w-full object-cover"
            />
          ) : (
            <div className="flex h-32 w-full items-center justify-center">
              <ImageOff className="h-6 w-6 text-navy-700" />
            </div>
          )}
        </div>
        <a
          href={item.download_url}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-accent-500/50 bg-accent-500/10 px-2.5 py-1.5 text-xs font-medium text-accent-300 transition-colors hover:border-accent-400 hover:text-accent-100"
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
        <p className="truncate text-center font-mono text-[10px] text-navy-600" title={item.filename}>
          {item.filename}
        </p>
      </div>

      {/* Copyable metadata */}
      <div className="space-y-3">
        <Field
          index={index}
          label="Title"
          value={item.title}
          hint={`${item.title.length} chars`}
        />
        <Field
          label="Description"
          value={item.description}
          hint={`${item.description.length} chars`}
          multiline
        />
        <Field
          label="Keywords"
          value={item.keywords_csv}
          hint={`${keywordCount} keyword(s)`}
          multiline
        />
      </div>
    </article>
  );
}

function Field({
  index,
  label,
  value,
  hint,
  multiline = false,
}: {
  index?: number;
  label: string;
  value: string;
  hint?: string;
  multiline?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-navy-400">
          {index !== undefined ? `${index + 1}. ` : ""}
          {label}
          {hint && <span className="ml-2 font-normal normal-case text-navy-600">{hint}</span>}
        </span>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </div>
      <p
        className={`w-full rounded-md border border-navy-800 bg-navy-950/70 px-3 py-2 text-xs leading-relaxed text-navy-100 ${
          multiline ? "whitespace-pre-wrap" : ""
        }`}
      >
        {value || <span className="text-navy-600">(empty)</span>}
      </p>
    </div>
  );
}
