"use client";

/**
 * The Prompt Library section: header with totals, the search/filter card, and
 * the card grid with its loading and empty states.
 *
 * A pure view of `usePromptLibrary` — the hook owns the debounce, the
 * monotonic-request loading discipline, and the mutations. Rendered under the
 * library route's page header, so this row carries only the count line.
 */
import GroupBar from "@/components/prompts/GroupBar";
import LibraryFilters from "@/components/prompts/LibraryFilters";
import PromptLibraryGrid from "@/components/prompts/PromptLibraryGrid";
import type { UsePromptLibraryResult } from "@/hooks/usePromptLibrary";

interface LibrarySectionProps {
  library: UsePromptLibraryResult;
}

export default function LibrarySection({ library }: LibrarySectionProps) {
  return (
    <section aria-label="Prompt library">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="label-caps">All prompts</p>
        <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
          {library.totals.total} total
        </span>
      </div>

      {library.error && (
        <p
          className="mb-3 rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
          role="alert"
        >
          {library.error}
        </p>
      )}
      {library.notice && (
        <p
          className="mb-3 cursor-pointer rounded-sm border border-olive-500/60 bg-olive-400/10 px-3 py-2 text-sm text-olive-400"
          role="status"
          onClick={library.clearNotice}
          title="Dismiss"
        >
          {library.notice}
        </p>
      )}

      <div className="frame-card px-5 py-4">
        <LibraryFilters
          query={library.query}
          onQueryChange={library.setQuery}
          filter={library.filter}
          onFilterChange={library.setFilter}
          totals={library.totals}
        />

        {/* Folders: chips filter the grid; the bar groups the selection. */}
        <div className="mt-3 border-t border-dashed border-parchment-400 pt-3">
          <GroupBar
            groups={library.groups}
            activeGroup={library.group}
            onGroupFilter={library.setGroup}
            selectedCount={library.selectedIds.length}
            onClearSelection={library.clearSelection}
            onGroupSelection={library.groupSelection}
            isBusy={library.isGrouping}
          />
        </div>
      </div>

      <div className="mt-4">
        <PromptLibraryGrid
          prompts={library.prompts}
          isLoading={library.isLoading}
          busyPromptId={library.busyPromptId}
          filter={library.filter}
          query={library.query}
          group={library.group}
          selectedIds={library.selectedIds}
          onToggleSelected={library.toggleSelected}
          onToggleStatus={(prompt) =>
            void library.setPromptStatus(
              prompt.id,
              prompt.status === "USED" ? "DRAFT" : "USED"
            )
          }
          onDelete={(prompt) => void library.removePrompt(prompt.id)}
        />
      </div>
    </section>
  );
}
