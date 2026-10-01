"use client";

import {
  AlertTriangle,
  Check,
  ChevronRight,
  Download,
  Globe,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import {
  clearPrioritySources,
  downloadSourceTemplate,
  fetchPrioritySources,
  sourceHost,
  uploadPrioritySources,
  type PrioritySourceFile,
} from "@/lib/researchSources";

export interface PrioritySourcesPanelProps {
  disabled?: boolean;
  className?: string;
}

/**
 * The operator's priority-source list: hidden by default, expandable, uploadable.
 *
 * **Collapsed by default** as the operator asked, because it is a setting they
 * touch occasionally, not a control they use every run. It stays collapsed but
 * shows a count when a file *is* loaded, so the feature is never invisible while
 * it is affecting results.
 *
 * Two decisions worth stating:
 *
 * * **A downloadable template, not documentation.** The operator asked to be able
 *   to see the exact format, and a file that uploads *unchanged* is a better
 *   specification than a description of one — it proves the format works.
 * * **The upload sends the file's text, unparsed.** The server is the only thing
 *   that decides validity, so a malformed file cannot look like a successful
 *   upload that silently did nothing.
 */
export default function PrioritySourcesPanel({
  disabled = false,
  className,
}: PrioritySourcesPanelProps) {
  const [isOpen, setOpen] = useState(false);
  const [stored, setStored] = useState<PrioritySourceFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isBusy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setStored(await fetchPrioritySources());
    } catch (problem) {
      setError((problem as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleDownloadTemplate = useCallback(async () => {
    setError(null);
    try {
      await downloadSourceTemplate();
    } catch (problem) {
      setError((problem as Error).message);
    }
  }, []);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setNotice(null);
      setBusy(true);
      try {
        // Read as text and send it verbatim: parsing here would hide a format
        // error behind a successful upload.
        const text = await file.text();
        const outcome = await uploadPrioritySources(text, file.name);
        setStored(outcome);
        setNotice(
          `Loaded ${outcome.sources.length} source${
            outcome.sources.length === 1 ? "" : "s"
          } from ${outcome.filename || file.name}.`
        );
      } catch (problem) {
        // The backend answers a bad file with a 400 and the reason, so surface it
        // rather than a generic failure — the operator is editing a file.
        const message = (problem as Error).message;
        setError(message);
      } finally {
        setBusy(false);
        // Cleared so re-selecting the same file fires `change` again.
        if (inputRef.current) inputRef.current.value = "";
      }
    },
    []
  );

  const handleClear = useCallback(async () => {
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      setStored(await clearPrioritySources());
      setNotice("Priority sources removed. Research will use general search only.");
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  const count = stored?.sources.length ?? 0;
  const warnings = stored?.warnings ?? [];

  return (
    <section
      className={cn(
        "overflow-hidden rounded-xl border border-navy-700/50 bg-navy-850/40",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-navy-800/40"
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 text-navy-400 transition-transform",
            isOpen && "rotate-90"
          )}
          aria-hidden
        />
        <Globe className="h-3.5 w-3.5 shrink-0 text-navy-400" aria-hidden />
        <span className="text-xs font-semibold text-navy-200">
          Priority sources
        </span>
        <span className="text-[11px] text-navy-400">
          {count > 0
            ? `${count} site${count === 1 ? "" : "s"} preferred by the agent`
            : "Upload sites the agent should trust first"}
        </span>
        {count > 0 ? (
          <span className="ml-auto flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-300">
            <Check className="h-2.5 w-2.5" aria-hidden />
            Active
          </span>
        ) : null}
      </button>

      {isOpen ? (
        <div className="space-y-3 border-t border-navy-700/40 px-3 py-3">
          <p className="text-[11px] leading-relaxed text-navy-400">
            Every general search is a fallback chain, and it can degrade quietly:
            when the index is blocked the agent gets news coverage instead of
            catalogue pages, and reports an empty market that was never actually
            searched. Listing the sites that carry the evidence makes the agent
            restrict its queries to them (
            <code className="text-navy-300">site:</code>) and open their pages
            instead of settling for a snippet — so the answer no longer depends on
            which index answered.
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={inputRef}
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
              icon={<Upload className="h-3.5 w-3.5" aria-hidden />}
              disabled={disabled || isBusy}
              onClick={() => inputRef.current?.click()}
            >
              Upload JSON
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<Download className="h-3.5 w-3.5" aria-hidden />}
              disabled={isBusy}
              onClick={handleDownloadTemplate}
            >
              Download template
            </Button>
            {count > 0 ? (
              <Button
                size="sm"
                variant="ghost"
                icon={<Trash2 className="h-3.5 w-3.5" aria-hidden />}
                disabled={disabled || isBusy}
                onClick={handleClear}
              >
                Remove
              </Button>
            ) : null}
          </div>

          {error ? (
            <p className="flex gap-2 rounded-lg border border-red-500/30 bg-red-500/5 px-2.5 py-2 text-[11px] leading-relaxed text-red-200">
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
              <span>{error}</span>
            </p>
          ) : null}
          {notice ? (
            <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-2.5 py-2 text-[11px] leading-relaxed text-emerald-200">
              {notice}
            </p>
          ) : null}
          {warnings.map((warning) => (
            <p
              key={warning}
              className="flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-2.5 py-2 text-[11px] leading-relaxed text-amber-200"
            >
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
              <span>{warning}</span>
            </p>
          ))}

          {count > 0 ? (
            <div className="space-y-1">
              <h4 className="text-[10px] font-semibold uppercase tracking-wide text-navy-400">
                Loaded sources
                {stored?.filename ? (
                  <span className="ml-1 font-normal normal-case text-navy-500">
                    from {stored.filename}
                  </span>
                ) : null}
              </h4>
              <ul className="space-y-1">
                {stored?.sources.map((source) => (
                  <li
                    key={source.url}
                    className="rounded-lg border border-navy-700/40 bg-navy-900/30 px-2.5 py-1.5"
                  >
                    <div className="flex items-baseline gap-2">
                      <span className="text-[11px] font-medium text-navy-200">
                        {source.name || sourceHost(source)}
                      </span>
                      <span className="text-[10px] text-navy-500">
                        {sourceHost(source)}
                      </span>
                      <span className="ml-auto text-[10px] text-navy-500">
                        priority {source.priority}
                      </span>
                    </div>
                    {source.notes ? (
                      <p className="mt-0.5 text-[10px] leading-relaxed text-navy-400">
                        {source.notes}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
