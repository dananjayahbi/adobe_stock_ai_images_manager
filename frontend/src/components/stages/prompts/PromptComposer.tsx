"use client";

import { Check, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { derivePromptTitle, type Prompt, type PromptDraft } from "@/lib/prompts";

export interface PromptComposerProps {
  /** The prompt being edited, or null when composing a new one. */
  prompt: Prompt | null;
  isBusy?: boolean;
  /** Optional failure message, shown inside the block. */
  error?: string | null;
  onSave: (draft: PromptDraft, promptId?: string) => Promise<unknown>;
  onCancel: () => void;
}

interface FormState {
  title: string;
  body: string;
  negative: string;
  tags: string;
}

const EMPTY: FormState = { title: "", body: "", negative: "", tags: "" };

const FIELD_CLASS = cn(
  "w-full rounded-lg border border-navy-700/60 bg-navy-900/60 px-2.5 py-1.5",
  "text-xs text-navy-50 placeholder:text-navy-500",
  "focus:border-accent-500/70 focus:outline-none focus:ring-1 focus:ring-accent-500/40"
);

/**
 * Inline prompt composer.
 *
 * Adding a prompt is a two-field job, so it happens **in the library list**
 * rather than in a modal: a dialog would hide the images on the left, and the
 * whole point of the split screen is to write a prompt while looking at what
 * it produced. The block appears exactly where the prompt will land.
 *
 * The title is optional and left blank by default — prompts are written as
 * free text, so forcing a name first is friction for no gain. The derived
 * title is previewed live so the operator can see what the library will show.
 */
export function PromptComposer({
  prompt,
  isBusy = false,
  error = null,
  onSave,
  onCancel,
}: PromptComposerProps) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [localError, setLocalError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLTextAreaElement>(null);

  // Reset and focus whenever the composer opens for a different prompt.
  useEffect(() => {
    setLocalError(null);
    setForm(
      prompt
        ? {
            title: prompt.title,
            body: prompt.body,
            negative: prompt.negative_prompt ?? "",
            tags: (prompt.tags ?? []).join(", "),
          }
        : EMPTY
    );
    if (!prompt) bodyRef.current?.focus();
  }, [prompt]);

  const derivedTitle = derivePromptTitle(form.body);
  const canSave = form.body.trim().length > 0 && !isBusy;

  async function handleSave() {
    if (!canSave) return;
    setLocalError(null);
    try {
      await onSave(
        {
          title: form.title.trim(),
          body: form.body.trim(),
          negative_prompt: form.negative.trim(),
          tags: form.tags
            .split(",")
            .map((tag) => tag.trim())
            .filter(Boolean),
        },
        prompt?.id
      );
    } catch (err) {
      // Stay open so the failure is readable next to the field that caused it.
      setLocalError(err instanceof Error ? err.message : "Could not save the prompt.");
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // Ctrl/Cmd+Enter saves from anywhere in the block; Escape abandons it.
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      void handleSave();
    } else if (event.key === "Escape") {
      event.preventDefault();
      onCancel();
    }
  }

  const message = localError ?? error;

  return (
    <div
      onKeyDown={handleKeyDown}
      className="space-y-2 rounded-xl border border-accent-500/50 bg-navy-850/80 p-3 shadow-glow-sm"
    >
      <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-accent-300">
        {prompt ? "Editing prompt" : "New prompt"}
      </p>

      <textarea
        ref={bodyRef}
        value={form.body}
        onChange={(event) =>
          setForm((current) => ({ ...current, body: event.target.value }))
        }
        rows={4}
        placeholder="A serene ayurvedic herb arrangement on a rustic wooden table, soft morning light…"
        aria-label="Prompt"
        className={cn(FIELD_CLASS, "resize-y")}
      />

      <input
        value={form.title}
        onChange={(event) =>
          setForm((current) => ({ ...current, title: event.target.value }))
        }
        placeholder={derivedTitle}
        aria-label="Title (optional)"
        className={FIELD_CLASS}
      />

      <textarea
        value={form.negative}
        onChange={(event) =>
          setForm((current) => ({ ...current, negative: event.target.value }))
        }
        rows={2}
        placeholder="Negative prompt (optional)"
        aria-label="Negative prompt"
        className={cn(FIELD_CLASS, "resize-y")}
      />

      <input
        value={form.tags}
        onChange={(event) =>
          setForm((current) => ({ ...current, tags: event.target.value }))
        }
        placeholder="Tags, comma separated"
        aria-label="Tags"
        className={FIELD_CLASS}
      />

      {!form.title.trim() && form.body.trim() ? (
        <p className="text-[10px] text-navy-400">
          Saves as <span className="text-navy-200">“{derivedTitle}”</span>
        </p>
      ) : null}

      {message ? (
        <p role="alert" className="text-[11px] text-red-300">
          {message}
        </p>
      ) : null}

      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={!canSave}
          isLoading={isBusy}
          onClick={() => void handleSave()}
          icon={isBusy ? undefined : <Check className="h-3.5 w-3.5" aria-hidden />}
        >
          {prompt ? "Save" : "Add"}
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={isBusy}
          onClick={onCancel}
          icon={<X className="h-3.5 w-3.5" aria-hidden />}
        >
          Cancel
        </Button>
        <span className="ml-auto text-[10px] text-navy-500">⌘/Ctrl + Enter</span>
      </div>
    </div>
  );
}

export default PromptComposer;
