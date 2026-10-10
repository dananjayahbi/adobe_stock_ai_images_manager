"use client";

/**
 * Priority sources card: the operator's own list of sites the agent should
 * search first.
 *
 * Compact by design — a file the operator touches occasionally, not a control
 * used every run. Upload sends the file's *text* verbatim so the server is the
 * only thing that decides validity (a client-side parse would let a malformed
 * file look like a successful upload that silently did nothing), and a
 * downloadable template proves the format works rather than describing it.
 */
import { Download, Globe, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import Button from "@/components/ui/Button";
import {
  clearPrioritySources,
  downloadSourceTemplate,
  fetchPrioritySources,
  uploadPrioritySources,
  type PrioritySourceFile,
} from "@/lib/research";
import { errorClass, inputClass, labelClass, noticeClass } from "./fieldStyles";

export default function PrioritySourcesCard() {
  const [stored, setStored] = useState<PrioritySourceFile | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [isBusy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPrioritySources()
      .then((next) => {
        if (!cancelled) setStored(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load sources.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const upload = useCallback(async (content: string, filename: string) => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      const outcome = await uploadPrioritySources(content, filename);
      setStored(outcome);
      setPasteText("");
      setNotice(
        `Loaded ${outcome.sources.length} source${
          outcome.sources.length === 1 ? "" : "s"
        } from ${outcome.filename || filename}.`
      );
    } catch (err) {
      // The backend answers a bad file with a 400 and the reason — surface it,
      // since the operator is editing a file and needs the actual problem.
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      // Read as text and send it verbatim: parsing here would hide a format
      // error behind a "successful" upload.
      await upload(await file.text(), file.name);
    },
    [upload]
  );

  const handleClear = useCallback(async () => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      setStored(await clearPrioritySources());
      setNotice("Priority sources removed. Research uses general search only.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove sources.");
    } finally {
      setBusy(false);
    }
  }, []);

  const handleTemplate = useCallback(async () => {
    setError(null);
    try {
      await downloadSourceTemplate();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed.");
    }
  }, []);

  const count = stored?.sources.length ?? 0;

  return (
    <section aria-label="Priority sources" className="frame-card px-5 py-4">
      <div className="flex items-center gap-2">
        <Globe className="h-4 w-4 text-brass-400" aria-hidden />
        <p className="label-caps">Priority sources</p>
        {count > 0 && (
          <span className="ml-auto rounded-sm border border-olive-500/60 bg-olive-400/10 px-1.5 py-0.5 font-stamp text-[10px] uppercase tracking-[0.14em] text-olive-400">
            {count} loaded
          </span>
        )}
      </div>

      <p className="mt-2 text-sm text-ink-400">
        {stored?.filename
          ? `Loaded from ${stored.filename}. `
          : ""}
        Sites the agent prefers when it searches. Upload the JSON template with
        your own list.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
        <Button
          size="sm"
          variant="secondary"
          type="button"
          loading={isBusy}
          onClick={() => fileRef.current?.click()}
        >
          <Upload className="h-3.5 w-3.5" aria-hidden />
          Upload JSON
        </Button>
        <Button size="sm" variant="ghost" type="button" onClick={() => void handleTemplate()}>
          <Download className="h-3.5 w-3.5" aria-hidden />
          Template
        </Button>
        {count > 0 && (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={isBusy}
            onClick={() => void handleClear()}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
            Remove
          </Button>
        )}
      </div>

      <div className="mt-3">
        <label htmlFor="priority-sources-paste" className={labelClass}>
          …or paste the file contents
        </label>
        <textarea
          id="priority-sources-paste"
          rows={3}
          value={pasteText}
          disabled={isBusy}
          placeholder='{"version": 1, "sources": [...]}'
          onChange={(event) => setPasteText(event.target.value)}
          className={`${inputClass} font-mono text-xs resize-y`}
        />
        <Button
          size="sm"
          variant="secondary"
          type="button"
          className="mt-2"
          loading={isBusy}
          disabled={!pasteText.trim()}
          onClick={() => void upload(pasteText, "pasted-sources.json")}
        >
          Upload pasted text
        </Button>
      </div>

      {(stored?.warnings ?? []).map((warning) => (
        <p key={warning} className={`${errorClass} mt-2`} role="alert">
          {warning}
        </p>
      ))}
      {error && (
        <p className={`${errorClass} mt-2`} role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className={`${noticeClass} mt-2`} role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
