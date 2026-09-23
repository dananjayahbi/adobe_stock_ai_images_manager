"use client";

import { Info, ListPlus, Loader2, Search, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import type { Prompt, PromptDraft, PromptFilter } from "@/lib/prompts";

import PromptBlock from "./PromptBlock";
import PromptComposer from "./PromptComposer";

export interface PromptSidebarProps {
  prompts: Prompt[];
  totals: { total: number; used: number; unused: number };
  filter: PromptFilter;
  onFilterChange: (next: PromptFilter) => void;
  isLoading: boolean;
  busyPromptId: string | null;
  /** Prompt highlighted by the last click/drag. */
  activePromptId: string | null;
  /** How many images are selected on the collection side. */
  selectedCount: number;
  /**
   * The prompt being composed or edited, or null when the composer is closed.
   *
   * `"new"` opens an empty composer at the top of the list; a prompt id opens
   * that prompt's block in edit mode, in place.
   */
  composing: "new" | string | null;
  composerError: string | null;
  onStartAdd: () => void;
  onSavePrompt: (draft: PromptDraft, promptId?: string) => Promise<unknown>;
  onCancelCompose: () => void;
  onSelect: (prompt: Prompt) => void;
  onEdit: (prompt: Prompt) => void;
  onDelete: (prompt: Prompt) => void;
  onBindSelection: (prompt: Prompt) => void;
  onToggleUsed: (prompt: Prompt) => void;
}

const FILTERS: { id: PromptFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "used", label: "Used" },
  { id: "unused", label: "Unused" },
  { id: "archived", label: "Archived" },
];

/**
 * The right-hand Prompt Library pane.
 *
 * Prompts are the *source* of the collected images, so the library is a peer of
 * the collection grid rather than a sub-panel of it. The search box filters
 * client-side because the library is a single operator's prompt list — a
 * round trip per keystroke would be slower and would fight the poll.
 */
export function PromptSidebar({
  prompts,
  totals,
  filter,
  onFilterChange,
  isLoading,
  busyPromptId,
  activePromptId,
  selectedCount,
  composing,
  composerError,
  onStartAdd,
  onSavePrompt,
  onCancelCompose,
  onSelect,
  onEdit,
  onDelete,
  onBindSelection,
  onToggleUsed,
}: PromptSidebarProps) {
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return prompts;
    return prompts.filter((prompt) => {
      const haystack = [
        prompt.title,
        prompt.body,
        prompt.negative_prompt ?? "",
        (prompt.tags ?? []).join(" "),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    });
  }, [prompts, query]);

  return (
    <Panel className="flex h-full min-h-0 flex-col overflow-hidden">
      <div className="space-y-3 border-b border-navy-700/40 p-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-accent-500/25 bg-accent-500/10 text-accent-300">
              <Sparkles className="h-3.5 w-3.5" aria-hidden />
            </span>
            <div className="min-w-0">
              <h2 className="truncate text-sm font-semibold text-navy-50">
                Prompt Library
              </h2>
              <p className="truncate text-[11px] text-navy-400">
                {totals.total} prompt{totals.total === 1 ? "" : "s"} ·{" "}
                <span className="text-emerald-300">{totals.used} used</span> ·{" "}
                {totals.unused} unused
              </p>
            </div>
          </div>

          <Button
            size="sm"
            variant="primary"
            onClick={onStartAdd}
            disabled={composing === "new"}
            icon={<ListPlus className="h-3.5 w-3.5" aria-hidden />}
          >
            Add
          </Button>
        </div>

        <div className="relative">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-500"
            aria-hidden
          />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search prompts…"
            aria-label="Search prompts"
            className={cn(
              "w-full rounded-lg border border-navy-700/60 bg-navy-900/60 py-1.5 pl-8 pr-2.5",
              "text-xs text-navy-50 placeholder:text-navy-500",
              "focus:border-accent-500/70 focus:outline-none focus:ring-1 focus:ring-accent-500/40"
            )}
          />
        </div>

        <div
          role="tablist"
          aria-label="Prompt filters"
          className="no-scrollbar -mx-0.5 flex items-center gap-1.5 overflow-x-auto px-0.5"
        >
          {FILTERS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="tab"
              aria-selected={filter === entry.id}
              onClick={() => onFilterChange(entry.id)}
              className={cn(
                "shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                filter === entry.id
                  ? "border-accent-500 bg-accent-500/15 text-accent-200"
                  : "border-navy-700/60 text-navy-300 hover:border-navy-600 hover:text-navy-100"
              )}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <p className="flex items-start gap-1.5 rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2 text-[11px] leading-relaxed text-navy-400">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-accent-400" aria-hidden />
          <span>
            Drag a prompt block onto an image to bind them, or select images and
            use <span className="text-navy-200">Bind</span>. One prompt can be
            bound to many images.
          </span>
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {/* The composer lives in the list, where the prompt will land. */}
        {composing === "new" ? (
          <PromptComposer
            prompt={null}
            isBusy={busyPromptId === "new"}
            error={composerError}
            onSave={onSavePrompt}
            onCancel={onCancelCompose}
          />
        ) : null}

        {isLoading && prompts.length === 0 ? (
          <div className="flex items-center justify-center gap-2 py-10 text-xs text-navy-400">
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
            Loading prompts…
          </div>
        ) : visible.length === 0 ? (
          <div className="rounded-xl border border-dashed border-navy-700/60 bg-navy-850/30 px-4 py-10 text-center">
            <p className="text-xs font-medium text-navy-200">
              {query.trim()
                ? "No prompts match your search"
                : filter === "all"
                  ? "No prompts yet"
                  : `No ${filter} prompts`}
            </p>
            <p className="mx-auto mt-1 max-w-xs text-[11px] leading-relaxed text-navy-400">
              {query.trim()
                ? "Try a different term, or clear the search."
                : "Add the prompt you used to generate an image, then drag it onto the image to link them."}
            </p>
            {!query.trim() && filter === "all" && composing !== "new" ? (
              <Button
                size="sm"
                variant="secondary"
                className="mt-3"
                onClick={onStartAdd}
                icon={<ListPlus className="h-3.5 w-3.5" aria-hidden />}
              >
                Add your first prompt
              </Button>
            ) : null}
          </div>
        ) : (
          visible.map((prompt) =>
            // Editing happens in place: the block is replaced by the composer,
            // so the operator edits the prompt exactly where it sits.
            composing === prompt.id ? (
              <PromptComposer
                key={prompt.id}
                prompt={prompt}
                isBusy={busyPromptId === prompt.id}
                error={composerError}
                onSave={onSavePrompt}
                onCancel={onCancelCompose}
              />
            ) : (
              <PromptBlock
                key={prompt.id}
                prompt={prompt}
                isActive={activePromptId === prompt.id}
                isBusy={busyPromptId === prompt.id}
                selectedCount={selectedCount}
                onSelect={onSelect}
                onEdit={onEdit}
                onDelete={onDelete}
                onBindSelection={onBindSelection}
                onToggleUsed={onToggleUsed}
              />
            )
          )
        )}
      </div>
    </Panel>
  );
}

export default PromptSidebar;
