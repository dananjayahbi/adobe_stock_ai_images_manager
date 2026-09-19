"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { downloadCsv, fetchCategories, fetchStages, type ImageRecord } from "@/lib/api";
import { useStageRecords } from "@/hooks/useStageRecords";
import { useStageSelection } from "@/hooks/useStageSelection";
import {
  STAGE_DEFINITIONS,
  formatScore,
  stageLabel,
  type AdobeCategory,
  type StageDefinition,
  type StageKey,
  type PipelineStage,
} from "@/lib/stages";

import CsvPanel from "./CsvPanel";
import MetadataEditorPanel from "./MetadataEditorPanel";
import StageActionBar from "./StageActionBar";
import StageBanner from "./StageBanner";
import StageCard from "./StageCard";
import StageInspectModal from "./StageInspectModal";
import StageJobPanel from "./StageJobPanel";
import StageRail from "./StageRail";
import StageSummaryCards from "./StageSummaryCards";

/**
 * Which stage key's action the bar triggers for a given stage.
 *
 * Terminal stages (OCR_REJECTED, INCOMPATIBLE) are absent on purpose: they have
 * no forward action, only review.
 */
const STAGE_TO_KEY: Partial<Record<PipelineStage, StageKey>> = {
  COLLECTED: "ocr",
  OCR_CLEAR: "upscale",
  UPSCALED: "refine",
  REFINED: "compatibility",
  COMPATIBLE: "metadata",
  METADATA_READY: "gallery",
};

export default function StageWorkspaceView() {
  const pipeline = useStageRecords();
  const selection = useStageSelection();

  const [stages, setStages] = useState<StageDefinition[]>(STAGE_DEFINITIONS);
  const [categories, setCategories] = useState<AdobeCategory[]>([]);
  const [inspectRecord, setInspectRecord] = useState<ImageRecord | null>(null);
  const [delaySeconds, setDelaySeconds] = useState(2);
  const [showCsvPanel, setShowCsvPanel] = useState(false);
  const [editingMetadata, setEditingMetadata] = useState<ImageRecord | null>(null);

  // Registry and categories are static; fetch once.
  useEffect(() => {
    void fetchStages()
      .then(setStages)
      .catch(() => {
        /* The local STAGE_DEFINITIONS fallback is already rendered. */
      });
    void fetchCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  // Keep the selection honest as records move between stages.
  const availableIds = useMemo(
    () => pipeline.records.map((record) => record.id),
    [pipeline.records]
  );
  const { prune } = selection;
  useEffect(() => {
    prune(availableIds);
  }, [availableIds, prune]);

  // Keep the inspected record in sync with polling refreshes.
  useEffect(() => {
    if (!inspectRecord) return;
    const refreshed = pipeline.records.find((r) => r.id === inspectRecord.id);
    if (refreshed && refreshed !== inspectRecord) setInspectRecord(refreshed);
  }, [pipeline.records, inspectRecord]);

  // Auto-dismiss transient success notices.
  useEffect(() => {
    if (!pipeline.notice) return;
    const timer = setTimeout(() => pipeline.clearNotice(), 4000);
    return () => clearTimeout(timer);
  }, [pipeline.notice, pipeline.clearNotice]);

  // Reset the selection when switching stages: a selection made in Stage 2 is
  // meaningless (and dangerous) once the grid shows Stage 6.
  const { setActiveStage } = pipeline;
  const { clear } = selection;
  useEffect(() => {
    clear();
    setEditingMetadata(null);
    setShowCsvPanel(false);
  }, [pipeline.activeStage, clear]);

  const stageKey = STAGE_TO_KEY[pipeline.activeStage];
  const eligible = stageKey
    ? pipeline.eligibleFor(stageKey)
    : pipeline.records;

  const handleRun = useCallback(() => {
    if (!stageKey) return;
    const ids =
      selection.count > 0 ? selection.selectedIds : eligible.map((r) => r.id);
    void pipeline.startStage({
      stageKey,
      recordIds: ids,
      delaySeconds: stageKey === "metadata" ? delaySeconds : undefined,
    });
  }, [stageKey, selection.selectedIds, selection.count, eligible, pipeline, delaySeconds]);

  const handleDownloadCsv = useCallback(() => {
    void downloadCsv(
      selection.count > 0 ? selection.selectedIds : undefined
    ).catch((err) =>
      pipeline.setError(err instanceof Error ? err.message : "Download failed.")
    );
  }, [selection.count, selection.selectedIds, pipeline]);

  const handleReset = useCallback(
    (updated: ImageRecord) => {
      setInspectRecord(updated);
      void pipeline.load();
    },
    [pipeline]
  );

  const handleMetadataSaved = useCallback(
    (updated: ImageRecord) => {
      setEditingMetadata(updated);
      setInspectRecord((current) => (current?.id === updated.id ? updated : current));
      void pipeline.load();
    },
    [pipeline]
  );

  const activeDefinition =
    stages.find((d) => d.stages.includes(pipeline.activeStage)) ?? stages[0];

  const isMetadataStage = pipeline.activeStage === "METADATA_READY";

  return (
    <div className="space-y-5">
      {pipeline.error && (
        <StageBanner tone="error" onDismiss={() => pipeline.setError(null)}>
          {pipeline.error}
        </StageBanner>
      )}

      {pipeline.notice && (
        <StageBanner tone="success" onDismiss={pipeline.clearNotice}>
          {pipeline.notice}
        </StageBanner>
      )}

      <StageSummaryCards summary={pipeline.summary} />

      <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="lg:sticky lg:top-20 lg:self-start">
          <StageRail
            activeStage={pipeline.activeStage}
            counts={pipeline.counts}
            onSelectStage={setActiveStage}
          />
        </aside>

        <div className="min-w-0 space-y-4">
          <header className="rounded-xl border border-zinc-800 bg-zinc-900/40 px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-sky-500/15 text-xs font-bold text-sky-300">
                {activeDefinition.number}
              </span>
              <h2 className="text-base font-semibold text-zinc-100">
                {activeDefinition.name}
              </h2>
              <span className="ml-auto text-xs text-zinc-500">
                {pipeline.records.length} image(s) in this stage
                {pipeline.activeStage === "COMPATIBLE" ||
                pipeline.activeStage === "INCOMPATIBLE"
                  ? ` · avg ${formatScore(pipeline.summary?.average_score ?? null)}`
                  : ""}
              </span>
            </div>
            <p className="mt-1.5 text-xs text-zinc-500">
              {activeDefinition.description}
            </p>
          </header>

          <StageActionBar
            stage={pipeline.activeStage}
            selectedCount={selection.count}
            eligibleCount={eligible.length}
            visibleCount={pipeline.records.length}
            isBusy={pipeline.isBusy}
            delaySeconds={delaySeconds}
            onDelayChange={setDelaySeconds}
            onRun={handleRun}
            onSelectAll={() => selection.selectMany(availableIds)}
            onClearSelection={selection.clear}
            onPreviewCsv={() => setShowCsvPanel(true)}
            onDownloadCsv={handleDownloadCsv}
          />

          {pipeline.job && (
            <StageJobPanel
              job={pipeline.job}
              onCancel={() => void pipeline.stopJob()}
              onDismiss={pipeline.clearJob}
            />
          )}

          {showCsvPanel && (
            <CsvPanel
              recordIds={
                selection.count > 0 ? selection.selectedIds : undefined
              }
              onClose={() => setShowCsvPanel(false)}
            />
          )}

          {isMetadataStage && editingMetadata && (
            <MetadataEditorPanel
              record={editingMetadata}
              categories={categories}
              onSaved={handleMetadataSaved}
            />
          )}

          {pipeline.isLoading && pipeline.records.length === 0 ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-800 py-16 text-zinc-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading {stageLabel(pipeline.activeStage)}…
            </div>
          ) : pipeline.records.length === 0 ? (
            <div className="rounded-xl border border-dashed border-zinc-800 px-6 py-16 text-center">
              <p className="text-sm text-zinc-400">
                No images in {stageLabel(pipeline.activeStage)}.
              </p>
              <p className="mt-1 text-xs text-zinc-600">
                {pipeline.activeStage === "COLLECTED"
                  ? "Upload images from the Pipeline page to start the workflow."
                  : "Run the previous stage to move images into this one."}
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {pipeline.records.map((record) => (
                <StageCard
                  key={record.id}
                  record={record}
                  isSelected={selection.isSelected(record.id)}
                  isRunning={
                    pipeline.job?.status === "running" &&
                    pipeline.job.items.some(
                      (item) =>
                        item.record_id === record.id && item.status === "running"
                    )
                  }
                  onToggleSelect={selection.toggle}
                  onInspect={(target) => {
                    setInspectRecord(target);
                    if (target.stage === "METADATA_READY") {
                      setEditingMetadata(target);
                    }
                  }}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      <StageInspectModal
        record={inspectRecord}
        isOpen={inspectRecord !== null}
        isBusy={pipeline.isBusy}
        onClose={() => setInspectRecord(null)}
        onReset={handleReset}
        previewVersion={inspectRecord?.updated_at}
      />
    </div>
  );
}
