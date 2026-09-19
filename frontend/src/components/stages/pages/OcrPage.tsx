"use client";

import { ArrowRight, ScanText, Undo2 } from "lucide-react";
import { useMemo } from "react";

import StageDeleteButton from "@/components/stages/StageDeleteButton";
import StagePageFrame, { type StageStat } from "@/components/stages/pages/StagePageFrame";
import { Button } from "@/components/ui/Button";
import { useStagePage } from "@/hooks/useStagePage";
import { STAGE_META, poolFor } from "@/lib/stageMeta";

const META = STAGE_META.ocr;

/**
 * Stage 2 — OCR Detector.
 *
 * The only page that scans for embedded text, and the only place the scan
 * action exists. It owns three buckets:
 *
 * - **Draft** — pushed here from the Collector and not scanned yet.
 * - **Clear** — scanned, no text found, safe to advance.
 * - **Rejected** — text found; the record leaves the pipeline.
 *
 * "Advance" here means *push to the next stage's queue*, never *run it* — the
 * upscale run belongs to the Upscale page.
 */
export default function OcrPage() {
  const controller = useStagePage();
  const { records, push, unpush, removeRecords, startStage, isBusy, isPushing, selection } =
    controller;

  const pool = useMemo(() => poolFor(records, "ocr"), [records]);

  const stats: StageStat[] = useMemo(() => {
    const draft = pool.filter((record) => record.queued_stage === "ocr").length;
    const clear = pool.filter((record) => record.stage === "OCR_CLEAR").length;
    const rejected = pool.filter((record) => record.stage === "OCR_REJECTED").length;
    const scanned = clear + rejected;

    return [
      { label: "Draft", value: draft, hint: "Not scanned yet", tone: "accent" },
      { label: "Clear", value: clear, hint: "No text found", tone: "success" },
      { label: "Rejected", value: rejected, hint: "Text detected", tone: "danger" },
      {
        label: "Pass rate",
        value: scanned > 0 ? `${Math.round((clear / scanned) * 100)}%` : "—",
        hint: `Of ${scanned} scanned`,
      },
    ];
  }, [pool]);

  return (
    <StagePageFrame
      meta={META}
      controller={controller}
      pool={pool}
      buckets={META.buckets}
      stats={stats}
      emptyTitle="Nothing in this bucket"
      emptyDescription="Push images here from the Collector, then select them and scan for embedded text."
      emptyAction={
        <span className="inline-flex items-center gap-1.5 text-xs text-navy-400">
          <ScanText className="h-3.5 w-3.5" aria-hidden />
          Waiting for images from the Collector
        </span>
      }
      renderActions={(visible) => {
        const selectedRecords = visible.filter((record) => selection.isSelected(record.id));
        const ids = selectedRecords.map((record) => record.id);

        // The scan action exists only for drafts — a record that has already
        // been scanned is not a draft, so it can only be moved on.
        const hasDrafts = selectedRecords.some((record) => record.queued_stage === "ocr");
        const canAdvance = selectedRecords.some(
          (record) => record.queued_stage === "ocr" || record.stage === "OCR_CLEAR"
        );

        return (
          <>
            {hasDrafts ? (
              <Button
                size="sm"
                variant="primary"
                disabled={isBusy}
                isLoading={isBusy}
                onClick={() => void startStage({ stageKey: "ocr", recordIds: ids })}
                icon={isBusy ? undefined : <ScanText className="h-3.5 w-3.5" aria-hidden />}
              >
                {META.action} ({selectedRecords.length})
              </Button>
            ) : null}

            {canAdvance ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={isPushing}
                onClick={() => void push("upscale", ids)}
                icon={<ArrowRight className="h-3.5 w-3.5" aria-hidden />}
              >
                Push to Upscale ({selectedRecords.length})
              </Button>
            ) : null}

            {hasDrafts ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={isPushing}
                onClick={() => void unpush("ocr", ids)}
                icon={<Undo2 className="h-3.5 w-3.5" aria-hidden />}
              >
                Back to draft
              </Button>
            ) : null}

            <StageDeleteButton
              recordIds={ids}
              filenames={selectedRecords.map((record) => record.filename)}
              disabled={isBusy}
              onDelete={removeRecords}
            />
          </>
        );
      }}
    />
  );
}
