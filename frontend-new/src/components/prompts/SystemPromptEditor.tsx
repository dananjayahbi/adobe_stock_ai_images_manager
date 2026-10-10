"use client";

/**
 * The per-mode system prompt editor.
 *
 * One tab per mode, a large textarea (no length limit — the context window is
 * the natural ceiling), Save, and a Reset that restores the shipped default.
 * The saved text is the system prompt for that mode, pasted in verbatim — the
 * server performs no substitutions. The server tells us which modes are
 * customised (`is_custom`), so the reset affordance cannot drift from the
 * backend.
 */
import { ChevronRight, RotateCcw, Save } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import Button from "@/components/ui/Button";
import {
  fetchSystemPrompts,
  saveSystemPrompt,
  type SystemPromptMode,
  type SystemPromptsDoc,
} from "@/lib/research";
import { errorClass, hintClass, inputClass, labelClass, noticeClass } from "./fieldStyles";

/** Tab order matches the served mode keys (backend `MODE_KEYS`). */
const TABS: Array<{ id: SystemPromptMode; label: string }> = [
  { id: "generate", label: "Generate" },
  { id: "research", label: "Research" },
  { id: "ideas", label: "Ideas" },
];

export default function SystemPromptEditor() {
  // Open by default: inside the settings modal it is the primary section, so
  // making the operator expand it first would only hide the content they came for.
  const [open, setOpen] = useState(true);
  const [doc, setDoc] = useState<SystemPromptsDoc | null>(null);
  const [tab, setTab] = useState<SystemPromptMode>("generate");
  const [draft, setDraft] = useState("");
  const [isLoading, setLoading] = useState(false);
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Load on first open: the modal mounts this only when shown, and a collapsed
  // section re-opened later must not refetch a doc it already holds.
  useEffect(() => {
    if (!open || doc) return;
    let cancelled = false;
    setLoading(true);
    fetchSystemPrompts()
      .then((next) => {
        if (cancelled) return;
        setDoc(next);
        setDraft(next.items["generate"] ?? "");
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load prompts.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, doc]);

  const selectTab = useCallback(
    (next: SystemPromptMode) => {
      setTab(next);
      setDraft(doc?.items[next] ?? "");
      setNotice(null);
      setError(null);
    },
    [doc]
  );

  const isCustom = Boolean(doc?.is_custom[tab]);
  const isDirty = doc ? draft !== (doc.items[tab] ?? "") : false;

  // Read inside stable callbacks without re-creating them on every keystroke.
  const tabRef = useRef(tab);
  tabRef.current = tab;

  const applyDoc = useCallback((next: SystemPromptsDoc) => {
    setDoc(next);
    // Repaint the box from the server's answer — it strips whitespace and an
    // empty value restores the default, so echoing our submit would show text
    // the model will not read.
    setDraft(next.items[tabRef.current] ?? "");
    setError(null);
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    setNotice(null);
    try {
      applyDoc(await saveSystemPrompt(tabRef.current, draft));
      setNotice("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the prompt.");
    } finally {
      setSaving(false);
    }
  }, [applyDoc, draft]);

  const reset = useCallback(async () => {
    setSaving(true);
    setNotice(null);
    try {
      applyDoc(await saveSystemPrompt(tabRef.current, ""));
      setNotice("Restored the shipped default.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset the prompt.");
    } finally {
      setSaving(false);
    }
  }, [applyDoc]);

  return (
    <section aria-label="System prompts" className="frame-card px-5 py-4">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left"
      >
        <ChevronRight
          className={`h-4 w-4 shrink-0 text-brass-400 transition-transform ${
            open ? "rotate-90" : ""
          }`}
          aria-hidden
        />
        <span className="label-caps">System prompts</span>
        <span className="ml-auto font-stamp text-[11px] text-ink-400">
          {open ? "close" : "open"}
        </span>
      </button>

      {open && (
        <div className="mt-4 space-y-3">
          <div role="tablist" aria-label="System prompt modes" className="flex flex-wrap gap-1.5">
            {TABS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                role="tab"
                aria-selected={tab === entry.id}
                onClick={() => selectTab(entry.id)}
                className={`rounded-sm border px-3 py-1.5 font-stamp text-[11px] uppercase tracking-[0.14em] transition-colors ${
                  tab === entry.id
                    ? "border-oxblood-500 bg-oxblood-500/10 text-oxblood-400"
                    : "border-parchment-500 text-ink-600 hover:border-brass-400 hover:text-ink-800"
                }`}
              >
                {entry.label}
                {doc?.is_custom[entry.id] && (
                  <span className="ml-1.5 text-brass-300" title="Customised">
                    ✦
                  </span>
                )}
              </button>
            ))}
          </div>

          {isLoading && !doc ? (
            <div className="h-40 animate-pulse rounded-sm bg-parchment-200" />
          ) : (
            <>
              <div>
                <label htmlFor="system-prompt-text" className={labelClass}>
                  {TABS.find((entry) => entry.id === tab)?.label} system prompt
                </label>
                <textarea
                  id="system-prompt-text"
                  value={draft}
                  rows={12}
                  disabled={isSaving}
                  onChange={(event) => setDraft(event.target.value)}
                  className={`${inputClass} font-mono resize-y leading-relaxed`}
                />
                <p className={hintClass}>
                  Saved text becomes the {TABS.find((entry) => entry.id === tab)?.label} system
                  prompt for every run in that mode, pasted in verbatim.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  type="button"
                  loading={isSaving}
                  disabled={!isDirty}
                  onClick={() => void save()}
                >
                  <Save className="h-3.5 w-3.5" aria-hidden />
                  Save
                </Button>
                {isCustom && (
                  <Button
                    size="sm"
                    variant="ghost"
                    type="button"
                    disabled={isSaving}
                    onClick={() => void reset()}
                  >
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                    Reset to default
                  </Button>
                )}
                {isCustom && !isDirty && (
                  <span className="text-xs text-brass-300">Customised</span>
                )}
              </div>

              {error && <p className={errorClass} role="alert">{error}</p>}
              {notice && <p className={noticeClass} role="status">{notice}</p>}
            </>
          )}
        </div>
      )}
    </section>
  );
}
