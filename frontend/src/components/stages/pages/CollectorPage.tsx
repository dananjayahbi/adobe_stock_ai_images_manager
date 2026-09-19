"use client";

import { ArrowRight, Database, Undo2 } from "lucide-react";
import { useMemo } from "react";

import StageDeleteButton from "@/components/stages/StageDeleteButton";
import StagePageFrame, { type StageStat } from "@/components/stages/pages/StagePageFrame";
import StageUploader from "@/components/stages/pages/StageUploader";
import { Button } from "@/components/ui/Button";
import { useStagePage } from "@/hooks/useStagePage";
import { COLLECTOR_META } from "@/lib/stageMeta";

/**
 * Stage 1 — Collector.
 *
 * Upload only. This page deliberately has **no** processing action: its job is
 * to hold images until the operator decides which ones to move forward. The
 * forward move is a *push* into the OCR Detector's queue, not a run — the scan
 * happens on the OCR page.
 */
export default function CollectorPage() {
  const controller = useStagePage();
  const { records, push, unpush, isPushing, removeRecords, selection } = controller;

  // Every record is visible here; the buckets decide what belongs where.
  const pool = records;

  const stats: StageStat[] = useMemo(() => {
    const inCollector = pool.filter(
      (record) => record.stage === "COLLECTED" && record.queued_stage !== "ocr"
    ).length;
    const pushed = pool.filter((record) => record.queued_stage === "ocr").length;
    const advanced = pool.filter((record) => record.stage !== "COLLECTED").length;

    return [
      { label: "In Collector", value: inCollector, tone: "accent" },
      { label: "Pushed to OCR", value: pushed, hint: "Awaiting a scan", tone: "warning" },
      { label: "Moved on", value: advanced, hint: "Past the OCR stage", tone: "success" },
      { label: "Total", value: pool.length },
    ];
  }, [pool]);

  return (
    <StagePageFrame
      meta={COLLECTOR_META}
      controller={controller}
      pool={pool}
      buckets={COLLECTOR_META.buckets}
      stats={stats}
      emptyTitle="No images in this bucket"
      emptyDescription="Upload JPEGs above, then select the ones you want and push them to the OCR Detector."
      emptyAction={
        <span className="inline-flex items-center gap-1.5 text-xs text-navy-400">
          <Database className="h-3.5 w-3.5" aria-hidden />
          Use the upload panel above
        </span>
      }
      panels={
        <StageUploader onUploaded={() => void controller.load()} disabled={isPushing} />
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
