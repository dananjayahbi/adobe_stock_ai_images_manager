"use client";

/**
 * One prompt in the library grid: title, clamped body (expandable), tags,
 * status badge, used date, and the copy / used-toggle / delete actions.
 *
 * The status badge reads `status`; `bound_count` stays on the type (the server
 * sends it) but is not rendered — the library no longer surfaces bindings.
 */
import { Check, Copy, Eye, EyeOff, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import { copyText, type Prompt } from "@/lib/prompts";
import { formatNaiveUtcDate } from "./dates";

interface PromptCardProps {
  prompt: Prompt;
  /** True while this prompt's own mutation is in flight. */
  isBusy: boolean;
  onToggleStatus: (prompt: Prompt) => void;
  onDelete: (prompt: Prompt) => void;
}

export default function PromptCard({
  prompt,
  isBusy,
  onToggleStatus,
  onDelete,
}: PromptCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setCopyState("idle");
  }, [prompt.body]);

  // A delete confirmation times out so a missed click does not arm the button
  // indefinitely.
  useEffect(() => {
    if (!confirmDelete) return;
    const timer = setTimeout(() => setConfirmDelete(false), 4000);
    return () => clearTimeout(timer);
  }, [confirmDelete]);

  const handleCopy = async () => {
    const ok = await copyText(prompt.body);
    setCopyState(ok ? "copied" : "failed");
    if (ok) setTimeout(() => setCopyState("idle"), 1800);
  };

  const statusBadge =
    prompt.status === "USED" ? (
      <Badge tone="success">Used</Badge>
    ) : prompt.status === "ARCHIVED" ? (
      <Badge tone="neutral">Archived</Badge>
    ) : (
      <Badge tone="info">Unused</Badge>
    );

  return (
    <article className="frame-card flex flex-col px-4 py-3">
      <div className="flex items-start justify-between gap-2">
        <h3 className="font-display text-base leading-snug text-ink-800">
          {prompt.title}
        </h3>
        {statusBadge}
      </div>

      <div className="mt-2 flex-1">
        <p
          className={`whitespace-pre-wrap break-words text-sm leading-relaxed text-ink-600 ${
            expanded ? "" : "line-clamp-4"
          }`}
        >
          {prompt.body}
        </p>
        {prompt.body.length > 220 && (
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            className="mt-1 inline-flex items-center gap-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 hover:text-brass-300"
          >
            {expanded ? (
              <>
                <EyeOff className="h-3 w-3" aria-hidden /> Less
              </>
            ) : (
              <>
                <Eye className="h-3 w-3" aria-hidden /> More
              </>
            )}
          </button>
        )}
      </div>

      {prompt.tags && prompt.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
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

      {prompt.status === "USED" && prompt.used_at && (
        <p className="mt-2 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
          used {formatNaiveUtcDate(prompt.used_at)}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-dashed border-parchment-400 pt-2.5">
        <Button
          size="sm"
          variant="ghost"
          type="button"
          onClick={() => void handleCopy()}
          title="Copy the prompt body"
        >
          {copyState === "copied" ? (
            <>
              <Check className="h-3 w-3 text-olive-400" aria-hidden /> Copied
            </>
          ) : copyState === "failed" ? (
            <span className="text-oxblood-400">Copy blocked</span>
          ) : (
            <>
              <Copy className="h-3 w-3" aria-hidden /> Copy
            </>
          )}
        </Button>

        {prompt.status !== "ARCHIVED" && (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            loading={isBusy}
            onClick={() => onToggleStatus(prompt)}
            title={
              prompt.status === "USED"
                ? "Mark this prompt unused (DRAFT)"
                : "Mark this prompt used (USED)"
            }
          >
            {prompt.status === "USED" ? "Mark unused" : "Mark used"}
          </Button>
        )}

        <Button
          size="sm"
          variant="ghost"
          type="button"
          className="ml-auto"
          disabled={isBusy}
          onClick={() => {
            if (confirmDelete) onDelete(prompt);
            else setConfirmDelete(true);
          }}
          title="Delete this prompt from the library"
        >
          <Trash2 className="h-3 w-3" aria-hidden />
          {confirmDelete ? "Sure?" : "Delete"}
        </Button>
      </div>
    </article>
  );
}
