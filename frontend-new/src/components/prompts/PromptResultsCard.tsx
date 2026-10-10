"use client";

/**
 * The prompts a run produced, with per-prompt selection, copy, and a one-click
 * route into the Prompt Library.
 *
 * Three deliberate behaviours (ported from the working implementation):
 *
 * * **Duplicates are shown but not pre-selected.** Hiding them would misreport
 *   how many prompts the model wrote; pre-selecting them would create the
 *   near-identical pair Adobe refuses. They render with the overlap reason and
 *   stay unchecked.
 * * **Warnings are attached to their prompt, not the run.** A house-rule
 *   violation is about one prompt; a run-level banner would not say which.
 * * **Copy reports failure.** A denied clipboard is otherwise
 *   indistinguishable from success, and the operator would paste stale text.
 */
import { AlertTriangle, Check, Copy, Save } from "lucide-react";
import { useEffect, useState } from "react";

import Button from "@/components/ui/Button";
import { copyText } from "@/lib/prompts";
import type { ResearchPrompt } from "@/lib/research";

/** Per-prompt metadata sent with the acceptance, matching the JSON contract. */
export interface PromptDetail {
  title?: string;
  tags?: string[];
  category?: number | null;
}

interface PromptResultsCardProps {
  prompts: ResearchPrompt[];
  /** Bodies already accepted, so they can be marked "in library". */
  acceptedBodies: string[];
  isSaving: boolean;
  /** The model's own one-line statement of what it produced. */
  summary?: string;
  onSave: (bodies: string[], details: PromptDetail[]) => void;
}

export default function PromptResultsCard({
  prompts,
  acceptedBodies,
  isSaving,
  summary,
  onSave,
}: PromptResultsCardProps) {
  const accepted = new Set(acceptedBodies);

  // Duplicates start unchecked; everything else starts checked. Recomputed when
  // a new result arrives, keyed on the prompt list so unrelated re-renders do
  // not wipe the operator's edits.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const signature = prompts.map((prompt) => prompt.index).join(",");

  useEffect(() => {
    setSelected(
      new Set(
        prompts.filter((prompt) => !prompt.duplicate).map((prompt) => prompt.index)
      )
    );
    // `signature` stands in for the array identity, which changes every render.
  }, [signature]); // eslint-disable-line react-hooks/exhaustive-deps

  if (prompts.length === 0) return null;

  const selectedPrompts = prompts.filter((prompt) => selected.has(prompt.index));

  const toggle = (index: number) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  return (
    <section aria-label="Prompts" className="frame-card px-5 py-4">
      <header className="flex flex-wrap items-center gap-2">
        <p className="label-caps">Prompts</p>
        <span className="rounded-sm border border-parchment-500 px-2 py-0.5 font-stamp text-[11px] tabular-nums text-ink-400">
          {prompts.length}
        </span>
        <Button
          size="sm"
          type="button"
          className="ml-auto"
          loading={isSaving}
          disabled={selectedPrompts.length === 0}
          onClick={() =>
            onSave(
              selectedPrompts.map((prompt) => prompt.body),
              selectedPrompts.map((prompt) => ({
                title: prompt.title,
                tags: prompt.tags,
                category: prompt.category,
              }))
            )
          }
        >
          <Save className="h-3.5 w-3.5" aria-hidden />
          Save {selectedPrompts.length} to library
        </Button>
      </header>

      {summary && (
        <p className="mt-2 text-sm leading-relaxed text-ink-400">{summary}</p>
      )}

      <ul className="mt-3 space-y-2">
        {prompts.map((prompt) => (
          <PromptRow
            key={prompt.index}
            prompt={prompt}
            isSelected={selected.has(prompt.index)}
            isAccepted={accepted.has(prompt.body)}
            onToggle={() => toggle(prompt.index)}
          />
        ))}
      </ul>
    </section>
  );
}

function PromptRow({
  prompt,
  isSelected,
  isAccepted,
  onToggle,
}: {
  prompt: ResearchPrompt;
  isSelected: boolean;
  isAccepted: boolean;
  onToggle: () => void;
}) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  // Reset the confirmation when the prompt body changes.
  useEffect(() => {
    setCopyState("idle");
  }, [prompt.body]);

  const handleCopy = async () => {
    const ok = await copyText(prompt.body);
    setCopyState(ok ? "copied" : "failed");
    if (ok) setTimeout(() => setCopyState("idle"), 1800);
  };

  return (
    <li
      className={`rounded-sm border px-3 py-2.5 transition-colors ${
        isSelected
          ? "border-brass-400/60 bg-brass-300/5"
          : "border-parchment-400 bg-parchment-100"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          aria-label={`Include prompt ${prompt.index}`}
          className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer accent-oxblood-500"
        />

        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span className="font-stamp text-ink-400">#{prompt.index}</span>
            {prompt.title && <span className="text-ink-800">{prompt.title}</span>}
            <span className="tabular-nums text-ink-400">{prompt.chars} chars</span>
            {prompt.category_name && (
              <span
                className="rounded-sm border border-parchment-500 px-1.5 py-0.5 text-ink-600"
                title={`Adobe category code ${prompt.category}`}
              >
                {prompt.category_name}
              </span>
            )}
            {isAccepted && (
              <span className="rounded-sm border border-olive-500/60 bg-olive-400/10 px-1.5 py-0.5 text-olive-400">
                In library
              </span>
            )}
            {prompt.duplicate && (
              <span className="rounded-sm border border-brass-400/60 bg-brass-300/10 px-1.5 py-0.5 text-brass-300">
                Overlaps #{prompt.duplicate_of}
              </span>
            )}
          </div>

          <p className="text-sm leading-relaxed text-ink-600">{prompt.body}</p>

          {prompt.notes && (
            <p className="text-xs italic leading-relaxed text-ink-400">
              {prompt.notes}
            </p>
          )}

          {prompt.tags && prompt.tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {prompt.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-sm border border-parchment-400 px-1.5 py-0.5 text-[10px] text-ink-400"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {prompt.warnings.length > 0 && (
            <ul className="space-y-1">
              {prompt.warnings.map((warning, index) => (
                <li
                  key={index}
                  className="flex gap-1.5 rounded-sm border border-brass-400/40 bg-brass-300/10 px-2 py-1 text-xs leading-relaxed text-brass-300"
                >
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          )}

          <button
            type="button"
            onClick={() => void handleCopy()}
            className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] transition-colors ${
              copyState === "failed"
                ? "bg-oxblood-400/10 text-oxblood-400"
                : copyState === "copied"
                  ? "bg-olive-400/10 text-olive-400"
                  : "text-ink-400 hover:bg-parchment-200 hover:text-ink-800"
            }`}
          >
            {copyState === "copied" ? (
              <>
                <Check className="h-3 w-3" aria-hidden /> Copied
              </>
            ) : copyState === "failed" ? (
              <>
                <AlertTriangle className="h-3 w-3" aria-hidden /> Copy blocked —
                select the text
              </>
            ) : (
              <>
                <Copy className="h-3 w-3" aria-hidden /> Copy
              </>
            )}
          </button>
        </div>
      </div>
    </li>
  );
}
