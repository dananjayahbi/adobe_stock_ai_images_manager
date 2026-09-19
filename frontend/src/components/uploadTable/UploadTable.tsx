"use client";

import { ImageOff } from "lucide-react";

import type { UploadTableItem } from "@/lib/api";

import CopyButton from "@/components/CopyButton";
import UploadTableRow from "./UploadTableRow";

interface UploadTableProps {
  items: UploadTableItem[];
}

/** The generated copy/paste metadata table for Adobe Stock submissions. */
export default function UploadTable({ items }: UploadTableProps) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-navy-800 py-16 text-navy-400">
        <ImageOff className="h-7 w-7 text-navy-700" />
        <p className="text-sm">No metadata rows to display.</p>
      </div>
    );
  }

  const allTitles = items.map((item) => item.title).join("\n");
  const allDescriptions = items.map((item) => item.description).join("\n\n");
  const allKeywords = items.map((item) => item.keywords_csv).join("\n");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-navy-800 bg-navy-900/50 px-3 py-2">
        <span className="text-xs font-medium text-navy-300">
          Copy an entire column:
        </span>
        <CopyButton value={allTitles} label="All titles" />
        <CopyButton value={allDescriptions} label="All descriptions" />
        <CopyButton value={allKeywords} label="All keywords" />
      </div>

      <div className="space-y-3">
        {items.map((item, index) => (
          <UploadTableRow key={item.record_id} item={item} index={index} />
        ))}
      </div>
    </div>
  );
}
