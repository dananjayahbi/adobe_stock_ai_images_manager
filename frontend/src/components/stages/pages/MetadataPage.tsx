"use client";

import { ArrowRight, Download, PencilLine, Play, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import CsvPanel from "@/components/stages/CsvPanel";
import MetadataEditorPanel from "@/components/stages/MetadataEditorPanel";
import StageDeleteButton from "@/components/stages/StageDeleteButton";
import StagePageFrame, { type StageStat } from "@/components/stages/pages/StagePageFrame";
import { Button } from "@/components/ui/Button";
import { useStagePage } from "@/hooks/useStagePage";
import { fetchCategories, type ImageRecord } from "@/lib/api";
import { STAGE_META, poolFor } from "@/lib/stageMeta";
import type { AdobeCategory } from "@/lib/stages";

const META = STAGE_META.metadata;

/**
 * Stage 6 — Metadata & CSV.
 *
 * Unlike the other stages this page needs per-record editing, so it drives
 * `StagePageFrame` directly instead of the generic runnable page: the editor
 * panel and the CSV export both hang off the *current selection*.
 */
export default function MetadataPage() {
  const controller = useStagePage();
  const { records, push, removeRecords, startStage, isBusy, isPushing, selection } =
    controller;

  const [categories, setCategories] = useState<AdobeCategory[]>([]);
  const [editing, setEditing] = useState<ImageRecord | null>(null);
  const [showCsv, setShowCsv] = useState(false);

  const pool = useMemo(() => poolFor(records, "metadata"), [records]);

  useEffect(() => {
    void fetchCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  // Keep the open editor in sync with polling refreshes.
  useEffect(() => {
    if (!editing) return;
    const refreshed = pool.find((record) => record.id === editing.id);
    if (refreshed && refreshed !== editing) setEditing(refreshed);
  }, [pool, editing]);

  const stats: StageStat[] = useMemo(() => {
    const draft = pool.filter((record) => record.queued_stage === "metadata").length;
    const ready = pool.filter((record) => record.stage === "METADATA_READY").length;
    const withTitle = pool.filter((record) => Boolean(record.generated_title)).length;

    return [
      { label: "Draft", value: draft, hint: "No metadata yet", tone: "accent" },
      { label: "Metadata ready", value: ready, hint: "Title + keywords set", tone: "success" },
      { label: "Titled", value: withTitle, hint: "Across this page" },
      { label: "Total", value: pool.length },
    ];
  }, [pool]);

  const selectedRecords = pool.filter((record) => selection.isSelected(record.id));
  const selectedIds = selectedRecords.map((record) => record.id);

  return (
    <>
      <StagePageFrame
        meta={META}
        controller={controller}
        pool={pool}
        buckets={META.buckets}
        stats={stats}
        emptyTitle="Nothing in this bucket"
        emptyDescription="Push compatible images here, then generate titles, descriptions and keywords."
        renderActions={(visible) => {
          const visibleIds = new Set(visible.map((record) => record.id));
          const ids = selectedIds.filter((id) => visibleIds.has(id));
          const selected = selectedRecords.filter((record) => visibleIds.has(record.id));
          const hasDrafts = selected.some((record) => record.queued_stage === "metadata");
          const processedIds = selected
            .filter((record) => record.queued_stage !== "metadata")
            .map((record) => record.id);

          return (
            <>
              {selected.length === 1 ? (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={isBusy}
                  onClick={() => setEditing(selected[0])}
                  icon={<PencilLine className="h-3.5 w-3.5" aria-hidden />}
                >
                  Edit metadata
                </Button>
              ) : null}

              {hasDrafts ? (
                <Button
                  size="sm"
                  variant="primary"
                  disabled={isBusy}
                  isLoading={isBusy}
                  onClick={() => void startStage({ stageKey: "metadata", recordIds: ids })}
                  icon={isBusy ? undefined : <Play className="h-3.5 w-3.5" aria-hidden />}
                >
                  {META.action} ({selected.length})
                </Button>
              ) : null}

              <Button
                size="sm"
                variant="secondary"
                onClick={() => setShowCsv(true)}
                icon={<Table2 className="h-3.5 w-3.5" aria-hidden />}
              >
                Preview CSV
              </Button>

              {selected.length > 0 ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowCsv(true)}
                  icon={<Download className="h-3.5 w-3.5" aria-hidden />}
                >
                  Export {selected.length} row{selected.length === 1 ? "" : "s"}
                </Button>
              ) : null}

              {processedIds.length > 0 ? (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={isPushing}
                  onClick={() => void push("gallery", processedIds)}
                  icon={<ArrowRight className="h-3.5 w-3.5" aria-hidden />}
                >
                  {META.pushLabel} ({processedIds.length})
                </Button>
              ) : null}

              <StageDeleteButton
                recordIds={ids}
                filenames={selected.map((record) => record.filename)}
                disabled={isBusy}
                onDelete={removeRecords}
              />
            </>
          );
        }}
      />

      {editing ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-navy-950/85 p-4 backdrop-blur-sm">
          <div className="my-6 w-full max-w-3xl rounded-xl border border-navy-700/60 bg-navy-900 shadow-raised">
            <MetadataEditorPanel
              record={editing}
              categories={categories}
              onSaved={(updated) => {
                setEditing(updated);
                void controller.load();
              }}
            />
            <div className="flex justify-end border-t border-navy-700/40 px-4 py-3">
              <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {showCsv ? (
        <CsvPanel
          recordIds={selectedIds.length > 0 ? selectedIds : undefined}
          onClose={() => setShowCsv(false)}
        />
      ) : null}
    </>
  );
}
