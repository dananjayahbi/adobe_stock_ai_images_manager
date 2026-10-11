"use client";

/**
 * The library's card grid, with its loading skeleton and empty state.
 *
 * A grid rather than a sidebar list: a prompt is a full artifact (title, body,
 * tags, status), and the operator browses for the one they want — cards give
 * the body enough room to be recognisable without opening it.
 */
import EmptyState from "@/components/ui/EmptyState";
import type { Prompt, PromptFilter } from "@/lib/prompts";
import PromptCard from "./PromptCard";

interface PromptLibraryGridProps {
  prompts: Prompt[];
  isLoading: boolean;
  busyPromptId: string | null;
  filter: PromptFilter;
  query: string;
  /** Active folder filter ("" = none) — named in the empty state. */
  group: string;
  /** Ids ticked for batch grouping. */
  selectedIds: string[];
  onToggleSelected: (promptId: string) => void;
  onToggleStatus: (prompt: Prompt) => void;
  onDelete: (prompt: Prompt) => void;
}

/** Empty-state copy per filter, so the panel never says "no prompts" wrongly. */
function emptyCopy(
  filter: PromptFilter,
  query: string,
  group: string
): { title: string; body: string } {
  if (group.trim()) {
    return {
      title: `“${group.trim()}” is empty`,
      body:
        "No prompts in this folder right now — pick some cards and move them in, or clear the folder filter.",
    };
  }
  if (query.trim()) {
    return {
      title: "No matches",
      body: `Nothing in the library matches “${query.trim()}”.`,
    };
  }
  switch (filter) {
    case "used":
      return { title: "No used prompts", body: "Nothing marked used yet." };
    case "unused":
    case "draft":
      return { title: "No unused prompts", body: "Every prompt has been marked used." };
    case "archived":
      return { title: "No archived prompts", body: "Nothing filed away yet." };
    default:
      return {
        title: "The library is empty",
        body: "Save prompts from a research run and they will appear here.",
      };
  }
}

export default function PromptLibraryGrid({
  prompts,
  isLoading,
  busyPromptId,
  filter,
  query,
  group,
  selectedIds,
  onToggleSelected,
  onToggleStatus,
  onDelete,
}: PromptLibraryGridProps) {
  if (isLoading && prompts.length === 0) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="frame-card h-44 animate-pulse bg-parchment-200" />
        ))}
      </div>
    );
  }

  if (prompts.length === 0) {
    const copy = emptyCopy(filter, query, group);
    return <EmptyState title={copy.title} body={copy.body} glyph="№" />;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {prompts.map((prompt) => (
        <PromptCard
          key={prompt.id}
          prompt={prompt}
          isBusy={busyPromptId === prompt.id}
          isSelected={selectedIds.includes(prompt.id)}
          onToggleSelected={onToggleSelected}
          onToggleStatus={onToggleStatus}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
