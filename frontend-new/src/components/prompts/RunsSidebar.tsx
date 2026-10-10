"use client";

/**
 * The saved-runs sidebar: every research conversation, newest first.
 *
 * Research is exploratory, so the runs are the unit of work — the operator
 * returns to a conversation to pick a proposed idea, answer "continue with
 * these confidence rates", or collect the prompts. Opening a run replays its
 * stored events through the same reducer the live stream uses.
 *
 * The mode badge uses `normalizeMode`, so legacy `static`/`batch` runs display
 * as `generate` — the same mapping the backend applies on input.
 */
import { MessageSquarePlus, Trash2 } from "lucide-react";

import { normalizeMode, type ResearchRunSummary } from "@/lib/research";
import { parseServerDate } from "./dates";

interface RunsSidebarProps {
  runs: ResearchRunSummary[];
  activeId: string | null;
  onSelect: (runId: string) => void;
  onNew: () => void;
  onDelete: (runId: string) => void;
  isLoading?: boolean;
}

/**
 * Short relative time, e.g. "3m ago".
 *
 * Goes through `parseServerDate` because the API serves naive UTC timestamps
 * which `new Date` would read as local time — skewing every age by the UTC
 * offset (a run finished minutes ago rendered as "6h ago").
 */
function relativeTime(iso: string): string {
  const date = parseServerDate(iso);
  if (!date) return "";
  const then = date.getTime();
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function RunsSidebar({
  runs,
  activeId,
  onSelect,
  onNew,
  onDelete,
  isLoading = false,
}: RunsSidebarProps) {
  return (
    <div className="flex min-h-0 flex-col">
      <div className="flex items-center gap-2 pb-2">
        <p className="label-caps">Saved runs</p>
        <span className="rounded-sm border border-parchment-500 px-1.5 py-0.5 font-stamp text-[11px] tabular-nums text-ink-400">
          {runs.length}
        </span>
        <button
          type="button"
          onClick={onNew}
          title="Start a new research run"
          className="ml-auto inline-flex items-center gap-1 rounded-sm px-2 py-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-oxblood-400 transition-colors hover:bg-oxblood-400/10"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />
          New
        </button>
      </div>

      <div className="space-y-1.5">
        {isLoading && runs.length === 0 && (
          <div className="h-16 animate-pulse rounded-sm bg-parchment-200" />
        )}

        {!isLoading && runs.length === 0 && (
          <p className="text-sm leading-relaxed text-ink-400">
            No runs yet. Describe a niche or idea and the agent will start.
          </p>
        )}

        {runs.map((run) => {
          const isActive = run.id === activeId;
          return (
            <div
              key={run.id}
              className={`group relative rounded-sm border transition-colors ${
                isActive
                  ? "border-oxblood-500/70 bg-oxblood-400/5"
                  : "border-parchment-400 hover:border-brass-400/60"
              }`}
            >
              <button
                type="button"
                onClick={() => onSelect(run.id)}
                className="block w-full px-3 py-2 pr-7 text-left"
              >
                <p
                  className={`line-clamp-2 text-sm ${
                    isActive ? "text-ink-800" : "text-ink-600"
                  }`}
                >
                  {run.title || run.seed_message || "Untitled run"}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-ink-400">
                  <span className="font-stamp uppercase tracking-[0.14em]">
                    {normalizeMode(run.mode)}
                  </span>
                  <span>·</span>
                  <span>{relativeTime(run.updated_at)}</span>
                  {run.prompt_count > 0 && (
                    <>
                      <span>·</span>
                      <span className="tabular-nums">{run.prompt_count} prompts</span>
                    </>
                  )}
                  {run.has_validity && (
                    <span className="rounded-sm border border-brass-400/60 px-1.5 text-brass-300">
                      scored
                    </span>
                  )}
                  {run.status === "FAILED" && (
                    <span className="rounded-sm border border-oxblood-500/60 px-1.5 text-oxblood-400">
                      failed
                    </span>
                  )}
                </p>
              </button>

              <button
                type="button"
                onClick={() => onDelete(run.id)}
                title="Delete this run"
                aria-label={`Delete ${run.title || "research run"}`}
                className="absolute right-1.5 top-1.5 rounded-sm p-1 text-ink-400 opacity-0 transition-opacity hover:bg-oxblood-400/10 hover:text-oxblood-400 focus:opacity-100 group-hover:opacity-100"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
