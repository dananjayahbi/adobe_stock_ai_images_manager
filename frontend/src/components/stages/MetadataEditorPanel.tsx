"use client";

import { Check, Copy, Loader2, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { updateMetadata, type ImageRecord } from "@/lib/api";
import type { AdobeCategory } from "@/lib/stages";

/** Adobe's published limits for the CSV Title and Keywords fields. */
const MAX_TITLE_LENGTH = 70;
const MAX_KEYWORDS = 49;

interface MetadataEditorPanelProps {
  record: ImageRecord;
  categories: AdobeCategory[];
  onSaved: (record: ImageRecord) => void;
}

/** Copy a value to the clipboard, reporting success so the button can confirm. */
function useCopyFeedback() {
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(null), 1500);
    return () => clearTimeout(timer);
  }, [copied]);

  const copy = useCallback(async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
    } catch {
      // Clipboard access can be denied; the field is still selectable.
      setCopied(null);
    }
  }, []);

  return { copied, copy };
}

/**
 * Manual metadata editing for a single image (Stage 6).
 *
 * Every field has its own copy button because the operator's workflow is
 * paste-into-Adobe: the title, the description, and the comma-separated keyword
 * list each go into a different portal field.
 */
export default function MetadataEditorPanel({
  record,
  categories,
  onSaved,
}: MetadataEditorPanelProps) {
  const [title, setTitle] = useState(record.generated_title ?? "");
  const [description, setDescription] = useState(record.generated_description ?? "");
  const [keywords, setKeywords] = useState<string[]>(record.generated_keywords ?? []);
  const [keywordDraft, setKeywordDraft] = useState("");
  const [category, setCategory] = useState<number>(
    record.category ?? categories[0]?.code ?? 8
  );
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { copied, copy } = useCopyFeedback();

  // Re-sync when the record changes or a poll delivers newer server state.
  useEffect(() => {
    setTitle(record.generated_title ?? "");
    setDescription(record.generated_description ?? "");
    setKeywords(record.generated_keywords ?? []);
    setCategory(record.category ?? categories[0]?.code ?? 8);
  }, [record.id, record.generated_title, record.generated_description, record.generated_keywords, record.category, categories]);

  const keywordsCsv = keywords.join(", ");

  const isDirty =
    title !== (record.generated_title ?? "") ||
    description !== (record.generated_description ?? "") ||
    category !== (record.category ?? categories[0]?.code ?? 8) ||
    keywordsCsv !== (record.generated_keywords ?? []).join(", ");

  const addKeyword = () => {
    const cleaned = keywordDraft.replace(/[,;]/g, " ").trim();
    if (!cleaned) return;
    setKeywords((current) =>
      current.some((k) => k.toLowerCase() === cleaned.toLowerCase())
        ? current
        : [...current, cleaned]
    );
    setKeywordDraft("");
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      const updated = await updateMetadata(record.id, {
        title,
        description,
        keywords,
        category,
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save metadata.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Metadata
        </h3>
        <span className="text-[11px] text-zinc-600">
          <span className={keywords.length > MAX_KEYWORDS ? "text-red-400" : undefined}>
            {keywords.length}/{MAX_KEYWORDS} keywords
          </span>
          {" · "}
          <span className={title.length > MAX_TITLE_LENGTH ? "text-red-400" : undefined}>
            {title.length}/{MAX_TITLE_LENGTH} title
          </span>
        </span>
      </div>

      {title.length > MAX_TITLE_LENGTH && (
        <p className="rounded border border-amber-500/40 bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-200">
          Adobe caps titles at {MAX_TITLE_LENGTH} characters. The CSV export will
          truncate this title.
        </p>
      )}

      {error && (
        <p className="rounded border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-xs text-red-200">
          {error}
        </p>
      )}

      <Field label="Title" onCopy={() => void copy("title", title)} copied={copied === "title"}>
        <textarea
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          rows={2}
          className="w-full resize-none rounded border border-zinc-700 bg-zinc-950/60 px-2.5 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
        />
      </Field>

      <Field
        label="Description"
        onCopy={() => void copy("description", description)}
        copied={copied === "description"}
      >
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={3}
          className="w-full resize-none rounded border border-zinc-700 bg-zinc-950/60 px-2.5 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
        />
      </Field>

      <Field
        label="Keywords (comma-separated)"
        onCopy={() => void copy("keywords", keywordsCsv)}
        copied={copied === "keywords"}
      >
        <textarea
          value={keywordsCsv}
          onChange={(event) =>
            setKeywords(
              event.target.value
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean)
            )
          }
          rows={4}
          className="w-full resize-none rounded border border-zinc-700 bg-zinc-950/60 px-2.5 py-2 text-sm text-zinc-100 outline-none focus:border-sky-500"
        />
      </Field>

      <div className="flex gap-2">
        <input
          value={keywordDraft}
          onChange={(event) => setKeywordDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addKeyword();
            }
          }}
          placeholder="Add a keyword and press Enter"
          className="flex-1 rounded border border-zinc-700 bg-zinc-950/60 px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-sky-500"
        />
        <button
          type="button"
          onClick={addKeyword}
          className="rounded border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800"
        >
          Add
        </button>
      </div>

      <label className="flex items-center justify-between gap-3 text-xs">
        <span className="text-zinc-500">Adobe category</span>
        <select
          value={category}
          onChange={(event) => setCategory(Number(event.target.value))}
          className="rounded border border-zinc-700 bg-zinc-950/60 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-sky-500"
        >
          {categories.map((option) => (
            <option key={option.code} value={option.code}>
              {option.code} — {option.name}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={isSaving || !isDirty}
        className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
      >
        {isSaving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Save className="h-4 w-4" />
        )}
        {isDirty ? "Save changes" : "Saved"}
      </button>
    </div>
  );
}

function Field({
  label,
  onCopy,
  copied,
  children,
}: {
  label: string;
  onCopy: () => void;
  copied: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-zinc-500">{label}</span>
        <button
          type="button"
          onClick={onCopy}
          aria-label={`Copy ${label}`}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-300"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3 text-emerald-400" />
              Copied
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" />
              Copy
            </>
          )}
        </button>
      </div>
      {children}
    </div>
  );
}
