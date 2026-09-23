"use client";

import { ArrowRight, PencilLine, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import CsvExportActions from "@/components/stages/delivery/CsvExportActions";
import ForceAcceptControl from "@/components/stages/delivery/ForceAcceptControl";
import RenameBar from "@/components/stages/delivery/RenameBar";
import RenamePanel from "@/components/stages/delivery/RenamePanel";
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
 * Why the bundle is unavailable here, shown in place of the button.
 *
 * A disabled control with no explanation is a dead end; this names the action
 * that resolves it.
 */
const BUNDLE_HINT =
  "Publishing is what stages the upload copy, so publish the selection first — then bundle it from the Gallery.";

/**
 * Stage 6 — Metadata & CSV.
 *
 * This is where the operator stops *processing* images and starts *delivering*
 * them, so the page carries three delivery concerns alongside the run action:
 *
 * * **Naming** — Adobe matches CSV rows to uploaded files by filename, so the
 *   name is part of the deliverable and must be fixable in bulk.
 * * **Forced acceptance** — the gate is a heuristic; the operator can override
 *   it, and the override is recorded rather than hidden.
 * * **CSV / ZIP** — generated from the current *selection*, never the whole
 *   stage, because an operator uploads a chosen batch.
 *
 * Unlike the other stages this page needs per-record editing, so it drives
 * `StagePageFrame` directly instead of the generic runnable page.
 */
export default function MetadataPage() {
  const controller = useStagePage();
  const { records, push, removeRecords, startStage, isBusy, isPushing, selection } =
    controller;

  const [categories, setCategories] = useState<AdobeCategory[]>([]);
  const [editing, setEditing] = useState<ImageRecord | null>(null);
  const [showRename, setShowRename] = useState(false);
  // Delivery messages are merged into the frame's single banner rather than
  // stacking a second one next to it.
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
    // Surfacing the named count makes it obvious how many assets still need a
    // deliberate upload filename before the CSV is trustworthy.
    const named = pool.filter((record) => Boolean(record.download_name)).length;

    return [
      { label: "Draft", value: draft, hint: "No metadata yet", tone: "accent" },
      { label: "Metadata ready", value: ready, hint: "Title + keywords set", tone: "success" },
      { label: "Named", value: named, hint: "Explicit upload filenames" },
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
        error={error ?? controller.error}
        notice={notice ?? controller.notice}
        onClearError={() => setError(null)}
        onClearNotice={() => setNotice(null)}
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
          // A bundle can only be built from records that have a staged file, and
          // at this stage that means an already-published one. Anything else is
          // a guaranteed 409, so the control is withheld rather than offered and
          // then refused.
          const canBundle = selected.some((record) => record.stage === "PUBLISHED");

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
                  title="Generate metadata for the selection — allowed even below the acceptance threshold"
                >
                  {META.action} ({selected.length})
                </Button>
              ) : null}

              {/* Naming, one click for the common case.

                  The model named each asset while looking at it, so its
                  proposal is applied directly; the editor stays available for
                  the cases that need a human decision. */}
              {selected.length > 0 ? (
                <RenameBar
                  records={selected}
                  disabled={isBusy}
                  onError={setError}
                  onNotice={setNotice}
                  onApplied={async () => {
                    await controller.load();
                  }}
                  onEdit={() => setShowRename((current) => !current)}
                />
              ) : null}

              {/* CSV/ZIP follow the selection and do NOT require the metadata
                  gate to have passed: a force-accepted record still needs a
                  CSV, and `onlyReady={false}` is what lets it through.

                  The bundle is a different matter. It contains the *staged*
                  files, and publishing is what stages one — so at this stage a
                  bundle can only ever fail with a 409, which is exactly what the
                  operator hit. Offering the control only where it can succeed is
                  better than explaining the failure after the click; the CSV
                  alone works here, and the button says where to get the bundle. */}
              <CsvExportActions
                selectedIds={ids}
                onlyReady={false}
                includeBundle={canBundle}
                bundleHint={BUNDLE_HINT}
                disabled={isBusy}
                onError={setError}
                onNotice={setNotice}
              />

              {/* The override is only offered where it can actually do
                  something, so the button never promises a no-op. */}
              {selected.some(
                (record) =>
                  record.stage === "INCOMPATIBLE" || record.stage === "COLLECTED"
              ) ? (
                <ForceAcceptControl
                  records={selected}
                  disabled={isBusy}
                  onError={setError}
                  onNotice={setNotice}
                  onAccepted={async () => {
                    await controller.load();
                  }}
                />
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

      {showRename && selectedRecords.length > 0 ? (
        <div className="px-1">
          <RenamePanel
            records={selectedRecords}
            onError={setError}
            onNotice={setNotice}
            onSaved={async () => {
              await controller.load();
            }}
            onClose={() => setShowRename(false)}
          />
        </div>
      ) : null}

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
    </>
  );
}
