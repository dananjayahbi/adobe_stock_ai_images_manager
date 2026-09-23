"use client";

import { ArrowRight, Undo2 } from "lucide-react";
import { useCallback, useState } from "react";

import GalleryUploadSlot from "@/components/stages/GalleryUploadSlot";
import StageDeleteButton from "@/components/stages/StageDeleteButton";
import StagePageFrame from "@/components/stages/pages/StagePageFrame";
import CollectorModeTabs, {
  type CollectorMode,
} from "@/components/stages/prompts/CollectorModeTabs";
import { useCollectorWorkspace } from "@/components/stages/prompts/useCollectorWorkspace";
import { Button } from "@/components/ui/Button";
import { useStagePage } from "@/hooks/useStagePage";
import type { ImageRecord } from "@/lib/api";
import { COLLECTOR_META } from "@/lib/stageMeta";

/**
 * Stage 1 — Collector.
 *
 * The only stage with **two working modes**, because there are two genuinely
 * different ways images arrive here:
 *
 * - **Advanced** (default) — the operator writes the generation prompts first,
 *   then collects the images those prompts produced and binds them. The screen
 *   splits: collection gallery on the left, Prompt Library on the right. A
 *   prompt block is dragged onto an image to link them, and one prompt can be
 *   bound to many images.
 * - **Quick upload** — upload-only, the original behaviour, for images whose
 *   prompt is unknown or irrelevant.
 *
 * Neither mode runs anything: the forward move is a *push* into the OCR
 * Detector's queue, and the scan happens on that page.
 */
export default function CollectorPage() {
  const controller = useStagePage();
  const { records, push, unpush, isPushing, removeRecords, selection } = controller;

  const [mode, setMode] = useState<CollectorMode>("advanced");

  // Every record is visible here; the buckets decide what belongs where.
  const pool = records;

  const selectedIds = selection.selectedIds;

  // Hooks cannot be called conditionally, so the workspace is always mounted
  // and `enabled` is what stops it fetching in Quick mode.
  const workspace = useCollectorWorkspace({
    selectedIds,
    enabled: mode === "advanced",
    onRecordsChanged: controller.load,
  });

  const promptTitleFor = useCallback(
    (record: ImageRecord) =>
      mode === "advanced" ? workspace.promptTitleFor(record) : null,
    [mode, workspace]
  );

  // The workspace owns prompt errors/notices; the frame renders one banner, so
  // they are merged here rather than rendered twice.
  const mergedError = workspace.error ?? controller.error;
  const mergedNotice = workspace.notice ?? controller.notice;

  return (
    <StagePageFrame
      meta={COLLECTOR_META}
      controller={controller}
      pool={pool}
      buckets={COLLECTOR_META.buckets}
      error={mergedError}
      notice={mergedNotice}
      onClearError={() => {
        workspace.setError(null);
        controller.setError(null);
      }}
      onClearNotice={() => {
        workspace.clearNotice();
        controller.clearNotice();
      }}
      emptyTitle="No images in this bucket"
      emptyDescription={
        mode === "advanced"
          ? "Use the first tile to add images, then drop a prompt block onto one to bind them."
          : "Use the first tile to add images, then push the ones you want to the OCR Detector."
      }
      sidePanel={mode === "advanced" ? workspace.sidePanel : undefined}
      headerExtra={<CollectorModeTabs mode={mode} onChange={setMode} />}
      onPromptDrop={mode === "advanced" ? workspace.onPromptDrop : undefined}
      promptTitleFor={promptTitleFor}
      gridLeadingSlot={
        // The upload slot is the first cell of the grid: adding images and
        // holding them are one surface, not two stacked sections.
        <GalleryUploadSlot
          onUploaded={() => void controller.load()}
          disabled={isPushing}
        />
      }
      renderActions={(visible) => {
        const visibleIds = new Set(visible.map((record) => record.id));
        const selectedHere = selection.selectedIds.filter((id) => visibleIds.has(id));
        const selectedRecords = visible.filter((record) =>
          selection.isSelected(record.id)
        );
        const canPush = selectedRecords.some((record) => record.queued_stage !== "ocr");
        const canUnpush = selectedRecords.some((record) => record.queued_stage === "ocr");
        const busy = isPushing;

        return (
          <>
            {mode === "advanced" ? workspace.actions : null}

            {canPush ? (
              <Button
                size="sm"
                variant="primary"
                disabled={busy}
                isLoading={busy}
                onClick={() => void push("ocr", selectedHere)}
                icon={
                  busy ? undefined : <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                }
              >
                Push to OCR Detector ({selectedRecords.length})
              </Button>
            ) : null}

            {canUnpush ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={busy}
                onClick={() => void unpush("ocr", selectedHere)}
                icon={<Undo2 className="h-3.5 w-3.5" aria-hidden />}
              >
                Remove from queue
              </Button>
            ) : null}

            <StageDeleteButton
              recordIds={selectedHere}
              filenames={selectedRecords.map((record) => record.filename)}
              disabled={busy}
              onDelete={removeRecords}
            />
          </>
        );
      }}
    />
  );
}
