"use client";

import { MessageSquarePlus, Search, Trash2 } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ResearchRunSummary } from "@/lib/research";

export interface ResearchThreadListProps {
  runs: ResearchRunSummary[];
  activeId: string | null;
  onSelect: (runId: string) => void;
  onNew: () => void;
  onDelete: (runId: string) => void;
  isLoading?: boolean;
  className?: string;
}

/** Short relative time, e.g. "3m ago". */
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/**
 * The operator's research threads.
 *
 * Research is exploratory, so the threads are the unit of work: the operator
 * returns to a conversation to pick one of the proposed ideas, to answer
 * "continue with these confidence rates", or to collect the prompts. Losing them
 * on a restart would mean re-running the research, which is why they are stored
 * rather than kept in memory.
 */
export default function ResearchThreadList({
  runs,
  activeId,
  onSelect,
  onNew,
  onDelete,
  isLoading = false,
  className,
}: ResearchThreadListProps) {
  return (
    <div className={cn("flex min-h-0 flex-col", className)}>
      <div className="flex items-center gap-2 px-1 pb-2">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-navy-400">
          <Search className="h-3.5 w-3.5" aria-hidden />
          Research threads
        </h2>
        <span className="rounded-full bg-navy-750/70 px-2 py-0.5 text-[11px] tabular-nums text-navy-400">
          {runs.length}
        </span>
        <button
          type="button"
          onClick={onNew}
          title="Start a new research thread"
          className="ml-auto inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-accent-300 transition-colors hover:bg-accent-500/15"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden />
          New
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-0.5">
        {isLoading && runs.length === 0 ? (
          <p className="px-1 py-2 text-xs text-navy-500">Loading threads…</p>
        ) : null}

        {!isLoading && runs.length === 0 ? (
          <p className="px-1 py-2 text-xs leading-relaxed text-navy-500">
            No research yet. Describe a niche or idea below and the agent will start.
          </p>
        ) : null}

        {runs.map((run) => {
          const isActive = run.id === activeId;
          return (
            <div
              key={run.id}
              className={cn(
                "group relative rounded-lg border px-2.5 py-2 transition-colors",
                isActive
                  ? "border-accent-500/50 bg-accent-500/10"
                  : "border-navy-700/40 bg-navy-850/40 hover:border-navy-600 hover:bg-navy-800/60"
              )}
            >
              <button
                type="button"
                onClick={() => onSelect(run.id)}
                className="block w-full pr-6 text-left"
              >
                <p
                  className={cn(
                    "line-clamp-2 text-xs font-medium",
                    isActive ? "text-accent-100" : "text-navy-200"
                  )}
                >
                  {run.title || run.seed_message || "Untitled research"}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-navy-500">
                  <span className="uppercase tracking-wide">{run.mode}</span>
                  <span>·</span>
                  <span>{relativeTime(run.updated_at)}</span>
                  {run.prompt_count > 0 ? (
                    <>
                      <span>·</span>
                      <span className="tabular-nums">{run.prompt_count} prompts</span>
                    </>
                  ) : null}
                  {run.has_validity ? (
                    <span className="rounded-full bg-navy-750/80 px-1.5 text-navy-400">
                      scored
                    </span>
                  ) : null}
                  {run.status === "FAILED" ? (
                    <span className="rounded-full bg-red-500/15 px-1.5 text-red-300">
                      failed
                    </span>
                  ) : null}
                </p>
              </button>

              <button
                type="button"
                onClick={() => onDelete(run.id)}
                title="Delete this thread"
                aria-label={`Delete ${run.title || "research thread"}`}
                className="absolute right-1.5 top-1.5 rounded-md p-1 text-navy-500 opacity-0 transition-opacity hover:bg-red-500/15 hover:text-red-300 focus:opacity-100 group-hover:opacity-100"
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
