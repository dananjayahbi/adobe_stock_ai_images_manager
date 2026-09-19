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
    <article className="grid gap-4 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 md:grid-cols-[10rem_1fr]">
      {/* Preview + download */}
      <div className="flex flex-col gap-2">
        <div className="overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950">
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
              <ImageOff className="h-6 w-6 text-zinc-700" />
            </div>
          )}
        </div>
        <a
          href={item.download_url}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border border-sky-500/50 bg-sky-500/10 px-2.5 py-1.5 text-xs font-medium text-sky-300 transition-colors hover:border-sky-400 hover:text-sky-100"
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </a>
        <p className="truncate text-center font-mono text-[10px] text-zinc-600" title={item.filename}>
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
        <span className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          {index !== undefined ? `${index + 1}. ` : ""}
          {label}
          {hint && <span className="ml-2 font-normal normal-case text-zinc-600">{hint}</span>}
        </span>
        <CopyButton value={value} label={`Copy ${label.toLowerCase()}`} />
      </div>
      <p
        className={`w-full rounded-md border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-xs leading-relaxed text-zinc-200 ${
          multiline ? "whitespace-pre-wrap" : ""
        }`}
      >
        {value || <span className="text-zinc-600">(empty)</span>}
      </p>
    </div>
  );
}
