"use client";

/**
 * The /prompts page's settings dialog: the four editors that shape every run
 * but don't belong in the workspace itself.
 *
 * 1. **System prompts** — the per-mode system prompt, the only content editor
 *    now that the house style has been merged into each mode's prompt.
 * 2. **Priority sources** — the operator's own list of sites to search first.
 * 3. **Blocked URLs** — pages ``fetch_page`` failed on and refuses to retry
 *    (the card hides itself when nothing is blocked).
 * 4. **Research tool budget** — the tool-call limit from app settings.
 *
 * Each section owns its own fetch/save; the modal only composes them, so
 * closing it mid-edit loses nothing that was saved and nothing uncommitted is
 * silently written.
 */
import BlockedUrlsCard from "@/components/prompts/BlockedUrlsCard";
import PrioritySourcesCard from "@/components/prompts/PrioritySourcesCard";
import SystemPromptEditor from "@/components/prompts/SystemPromptEditor";
import ToolBudgetCard from "@/components/prompts/ToolBudgetCard";
import Modal from "@/components/ui/Modal";

interface PageSettingsModalProps {
  open: boolean;
  onClose: () => void;
}

export default function PageSettingsModal({ open, onClose }: PageSettingsModalProps) {
  return (
    <Modal open={open} onClose={onClose} width="max-w-3xl" labelledBy="page-settings-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps">Prompts</p>
        <h2 id="page-settings-title" className="mt-0.5 font-display text-xl text-ink-800">
          Page settings
        </h2>
      </div>

      <div className="space-y-5 px-6 py-5">
        <SystemPromptEditor />
        <PrioritySourcesCard />
        <BlockedUrlsCard />
        <ToolBudgetCard />
      </div>
    </Modal>
  );
}
