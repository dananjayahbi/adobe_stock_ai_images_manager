"use client";

import { AlertTriangle, Copy, Check, Plus, Save } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";
import type { ResearchPrompt } from "@/lib/research";

export interface PromptResultCardProps {
  prompts: ResearchPrompt[];
  /** Prompts already accepted into the library, so they can be marked. */
  acceptedBodies: string[];
  isSaving: boolean;
  /** The model's own one-line statement of what it produced, from the JSON. */
  summary?: string;
  onSave: (bodies: string[], details: PromptDetail[]) => void;
  className?: string;
}

/** The per-prompt metadata sent with an acceptance, matching the JSON contract. */
export interface PromptDetail {
  title?: string;
  tags?: string[];
  category?: number | null;
}

/**
 * The prompts a run produced, with per-prompt accept and copy.
 *
 * Three deliberate behaviours:
 *
 * * **Duplicates are shown but not pre-selected.** Hiding them would make the
 *   operator think the model produced fewer prompts than it did; pre-selecting
 *   them would create the near-identical pair Adobe refuses. They are rendered
 *   with the overlap reason and left unchecked.
 * * **Warnings are attached to the prompt, not to the run.** A house-rule
 *   violation is about one specific prompt, and a run-level banner would not say
 *   which one to fix.
 * * **Copy reports failure.** A denied clipboard is otherwise indistinguishable
 *   from success, and the operator would paste stale text.
 */
export default function PromptResultCard({
  prompts,
  acceptedBodies,
  isSaving,
  summary,
  onSave,
  className,
}: PromptResultCardProps) {
  const accepted = new Set(acceptedBodies);

  // Duplicates start unchecked; everything else starts checked. Recomputed when
  // a new result arrives, keyed on the prompt list so the operator's edits are
  // not wiped by an unrelated re-render.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const signature = prompts.map((prompt) => prompt.index).join(",");

  useEffect(() => {
    setSelected(
      new Set(prompts.filter((prompt) => !prompt.duplicate).map((prompt) => prompt.index))
    );
    // `signature` stands in for the array identity, which changes on every render.
  }, [signature]); // eslint-disable-line react-hooks/exhaustive-deps

  if (prompts.length === 0) return null;

  const selectedPrompts = prompts.filter((prompt) => selected.has(prompt.index));
  const selectedBodies = selectedPrompts.map((prompt) => prompt.body);

  function toggle(index: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <section className={cn("space-y-3", className)}>
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-navy-400">
          Prompts
        </h3>
        <span className="rounded-full bg-navy-750/70 px-2 py-0.5 text-xs tabular-nums text-navy-300">
          {prompts.length}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            icon={<Save className="h-3.5 w-3.5" aria-hidden />}
            isLoading={isSaving}
            disabled={selectedBodies.length === 0}
            onClick={() =>
              onSave(
                selectedBodies,
                selectedPrompts.map((prompt) => ({
                  title: prompt.title,
                  tags: prompt.tags,
                  category: prompt.category,
                }))
              )
            }
          >
            Save {selectedBodies.length} to library
          </Button>
        </div>
      </header>

      {summary ? (
        <p className="text-xs leading-relaxed text-navy-300">{summary}</p>
      ) : null}

      <ul className="space-y-2.5">
        {prompts.map((prompt) => (
          <PromptCard
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

function PromptCard({
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

  // Reset the copy confirmation when the prompt body changes.
  useEffect(() => {
    setCopyState("idle");
  }, [prompt.body]);

  async function handleCopy() {
    const ok = await copyText(prompt.body);
    setCopyState(ok ? "copied" : "failed");
    if (ok) setTimeout(() => setCopyState("idle"), 1800);
  }

  return (
    <li
      className={cn(
        "rounded-xl border px-3 py-2.5 transition-colors",
        isSelected
          ? "border-accent-500/40 bg-navy-800/60"
          : "border-navy-700/40 bg-navy-850/40"
      )}
    >
      <div className="flex items-start gap-2.5">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          aria-label={`Include prompt ${prompt.index}`}
          className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer accent-accent-500"
        />

        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span className="font-semibold text-navy-400">#{prompt.index}</span>
            {prompt.title ? (
              <span className="font-medium text-navy-200">{prompt.title}</span>
            ) : null}
            <span className="tabular-nums text-navy-500">{prompt.chars} chars</span>
            {prompt.category_name ? (
              <span
                className="rounded-full bg-navy-750/70 px-2 py-0.5 text-navy-300"
                title={`Adobe category code ${prompt.category}`}
              >
                {prompt.category_name}
              </span>
            ) : null}
            {isAccepted ? (
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-emerald-300">
                In library
              </span>
            ) : null}
            {prompt.duplicate ? (
              <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-amber-300">
                Overlaps #{prompt.duplicate_of}
              </span>
            ) : null}
          </div>

          <p className="text-xs leading-relaxed text-navy-200">{prompt.body}</p>

          {prompt.notes ? (
            <p className="text-[11px] italic leading-relaxed text-navy-400">
              {prompt.notes}
            </p>
          ) : null}

          {prompt.tags && prompt.tags.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {prompt.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-md bg-navy-750/60 px-1.5 py-0.5 text-[10px] text-navy-300"
                >
                  {tag}
                </span>
              ))}
            </div>
          ) : null}

          {prompt.warnings.length > 0 ? (
            <ul className="space-y-1">
              {prompt.warnings.map((warning, index) => (
                <li
                  key={index}
                  className="flex gap-1.5 rounded-md bg-amber-500/10 px-2 py-1 text-[11px] leading-relaxed text-amber-200"
                >
                  <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          ) : null}

          <button
            type="button"
            onClick={handleCopy}
            className={cn(
              "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] transition-colors",
              copyState === "failed"
                ? "bg-red-500/15 text-red-300"
                : copyState === "copied"
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "text-navy-400 hover:bg-navy-750/70 hover:text-navy-200"
            )}
          >
            {copyState === "copied" ? (
              <>
                <Check className="h-3 w-3" aria-hidden /> Copied
              </>
            ) : copyState === "failed" ? (
              <>
                <AlertTriangle className="h-3 w-3" aria-hidden /> Copy blocked — select the text
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

export interface SaveHintProps {
  count: number;
}

/** A short line describing what saving does. */
export function SaveHint({ count }: SaveHintProps) {
  return (
    <p className="flex items-center gap-1.5 text-[11px] text-navy-500">
      <Plus className="h-3 w-3" aria-hidden />
      {count === 0
        ? "Select the prompts worth keeping."
        : `Saving adds ${count} draft prompt${count === 1 ? "" : "s"} to the Prompt Library.`}
    </p>
  );
}
