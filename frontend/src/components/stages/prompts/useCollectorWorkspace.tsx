"use client";

import { Link2Off } from "lucide-react";
import { useMemo, useState } from "react";

import PromptDeleteDialog from "@/components/stages/prompts/PromptDeleteDialog";
import PromptSidebar from "@/components/stages/prompts/PromptSidebar";
import { Button } from "@/components/ui/Button";
import { usePromptLibrary } from "@/hooks/usePromptLibrary";
import type { ImageRecord } from "@/lib/api";
import { type Prompt, type PromptDraft } from "@/lib/prompts";

export interface CollectorWorkspaceResult {
  /** Rendered beside the collection grid. */
  sidePanel: React.ReactNode;
  /** Extra selection-bar actions contributed by the prompt side. */
  actions: React.ReactNode;
  /** Passed to the grid so tiles accept a dropped prompt block. */
  onPromptDrop: (recordId: string, promptId: string) => void;
  /** Resolves the bound prompt's title for a record's tile badge. */
  promptTitleFor: (record: ImageRecord) => string | null;
  /** Errors raised by prompt operations, surfaced by the page's banner. */
  error: string | null;
  notice: string | null;
  clearNotice: () => void;
  setError: (message: string | null) => void;
}

export interface CollectorWorkspaceOptions {
  /** Images currently selected on the collection side. */
  selectedIds: string[];
  /** Refresh the record list after a bind/unbind. */
  onRecordsChanged: () => Promise<void> | void;
  /** False in Quick mode, which stops the library polling entirely. */
  enabled?: boolean;
}

/**
 * The Advanced mode's split workspace.
 *
 * Stage 1's real workflow is prompt-first: the prompt is written *before* the
 * image exists, so the Collector shows both halves of that relationship at
 * once — the collection gallery on the left, the Prompt Library on the right.
 *
 * This hook owns the prompt library plus the two gestures that link the halves:
 * dropping a prompt block onto an image, and binding the current image
 * selection to a prompt. Both funnel into one `bind` call, so the two paths
 * cannot drift.
 */
export function useCollectorWorkspace({
  selectedIds,
  onRecordsChanged,
  enabled = true,
}: CollectorWorkspaceOptions): CollectorWorkspaceResult {
  const library = usePromptLibrary(enabled);
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  /**
   * Which composer is open: `"new"` for a fresh block at the top of the list,
   * a prompt id for in-place editing, or null when the library is just a list.
   */
  const [composing, setComposing] = useState<"new" | string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Prompt | null>(null);
  const [isDeleting, setDeleting] = useState(false);

  const promptTitles = useMemo(() => {
    const map = new Map<string, string>();
    for (const prompt of library.prompts) map.set(prompt.id, prompt.title);
    return map;
  }, [library.prompts]);

  // The library is filtered server-side, so a bound prompt may be absent from
  // the visible list. Fall back to the record's own link rather than showing a
  // misleading "no prompt" badge.
  const titleFor = (record: ImageRecord): string | null => {
    if (!record.prompt_id) return null;
    return promptTitles.get(record.prompt_id) ?? "Linked prompt";
  };

  async function handleBind(promptId: string, recordIds: string[]) {
    if (recordIds.length === 0) return;
    await library.bind(promptId, recordIds);
    setActivePromptId(promptId);
    await onRecordsChanged();
  }

  const onPromptDrop = (recordId: string, promptId: string) => {
    void handleBind(promptId, [recordId]);
  };

  function openEditor(prompt: Prompt | null) {
    setComposing(prompt ? prompt.id : "new");
  }

  async function handleSave(draft: PromptDraft, promptId?: string) {
    const saved = await library.savePrompt(draft, promptId);
    setActivePromptId(saved.id);
    // Close the composer only on success; a failure keeps it open with the
    // message rendered inside the block.
    setComposing(null);
  }

  async function handleDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await library.removePrompt(pendingDelete.id);
      if (activePromptId === pendingDelete.id) setActivePromptId(null);
      await onRecordsChanged();
      setPendingDelete(null);
    } catch {
      // The library hook already surfaced the message; keep the dialog open so
      // the failure stays next to the action that caused it.
    } finally {
      setDeleting(false);
    }
  }

  function handleToggleUsed(prompt: Prompt) {
    const isUsed = prompt.bound_count > 0 || prompt.status === "USED";
    if (isUsed && prompt.bound_count > 0) {
      // Bound prompts are used by definition — the backend enforces this, so
      // the button would be a no-op. Say so instead of silently doing nothing.
      library.setError(
        `“${prompt.title}” has ${prompt.bound_count} bound image(s), so it stays marked used. Unbind them first.`
      );
      return;
    }
    void library.setPromptStatus(prompt.id, isUsed ? "DRAFT" : "USED");
  }

  const activePrompt = library.prompts.find((prompt) => prompt.id === activePromptId);

  const sidePanel = (
    <>
      <PromptSidebar
        prompts={library.prompts}
        totals={library.totals}
        filter={library.filter}
        onFilterChange={library.setFilter}
        isLoading={library.isLoading}
        busyPromptId={library.busyPromptId}
        activePromptId={activePromptId}
        selectedCount={selectedIds.length}
        composing={composing}
        composerError={library.error}
        onStartAdd={() => openEditor(null)}
        onSavePrompt={handleSave}
        onCancelCompose={() => {
          setComposing(null);
          library.setError(null);
        }}
        onSelect={(prompt) => setActivePromptId(prompt.id)}
        onEdit={openEditor}
        onDelete={setPendingDelete}
        onBindSelection={(prompt) => void handleBind(prompt.id, selectedIds)}
        onToggleUsed={handleToggleUsed}
      />

      <PromptDeleteDialog
        prompt={pendingDelete}
        isBusy={isDeleting}
        error={library.error}
        onConfirm={() => void handleDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );

  const actions = activePrompt ? (
    <>
      <Button
        size="sm"
        variant="secondary"
        disabled={selectedIds.length === 0}
        onClick={() => void handleBind(activePrompt.id, selectedIds)}
        title={`Bind the selection to “${activePrompt.title}”`}
      >
        Bind to “{activePrompt.title}”
      </Button>
      <Button
        size="sm"
        variant="ghost"
        disabled={selectedIds.length === 0}
        onClick={() => {
          void library
            .bind(activePrompt.id, selectedIds, true)
            .then(() => onRecordsChanged());
        }}
        icon={<Link2Off className="h-3.5 w-3.5" aria-hidden />}
      >
        Unbind
      </Button>
    </>
  ) : null;

  return {
    sidePanel,
    actions,
    onPromptDrop,
    promptTitleFor: titleFor,
    error: library.error,
    notice: library.notice,
    clearNotice: library.clearNotice,
    setError: library.setError,
  };
}

export default useCollectorWorkspace;
