"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useBatchPolling } from "@/hooks/useBatchPolling";
import { cancelBatch, runBatch, updateBatch, uploadToBatch } from "@/lib/batches";
import { createProfile } from "@/lib/profiles";
import Button from "@/components/ui/Button";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import StepCard from "@/components/process/StepCard";
import UploadZone from "@/components/process/UploadZone";
import RecordStrip from "@/components/process/RecordStrip";
import SaveProfileDialog from "@/components/process/SaveProfileDialog";
import type { BatchStep } from "@/lib/types";

/**
 * The processing page: the batch's steps (with configs when editable), an
 * upload zone, one Run button for the whole pipeline, and live per-step
 * progress. Intentionally simple — the pipeline runs end to end as a unit, so
 * there is no per-step copy of the image or per-step controls.
 */
export default function ProcessingPage() {
  const params = useParams<{ id: string }>();
  const batchId = params?.id;
  const { batch, error, refresh } = useBatchPolling(batchId);

  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);

  const running = batch?.status === "running";
  const editable = batch != null && batch.status !== "running";
  const hasImages = (batch?.record_count ?? 0) > 0;

  const handleFiles = useCallback(
    async (files: File[]) => {
      if (!batchId) return;
      setUploading(true);
      setUploadProgress(0);
      setActionError(null);
      try {
        const result = await uploadToBatch(batchId, files, setUploadProgress);
        setNotice(`Added ${result.count} image${result.count === 1 ? "" : "s"}.`);
        await refresh();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      } finally {
        setUploading(false);
      }
    },
    [batchId, refresh]
  );

  const handleConfigChange = useCallback(
    async (key: string, config: BatchStep["config"]) => {
      if (!batch) return;
      const steps = batch.steps.map((step) =>
        step.key === key ? { ...step, config } : step
      );
      // Optimistic: update local state via the poll's setter would require
      // exposing it; instead persist then refresh (config edits are rare).
      try {
        await updateBatch(batch.id, { steps });
        await refresh();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      }
    },
    [batch, refresh]
  );

  const handleRun = useCallback(async () => {
    if (!batchId) return;
    setBusy(true);
    setActionError(null);
    setNotice(null);
    try {
      await runBatch(batchId);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [batchId, refresh]);

  const handleCancel = useCallback(async () => {
    if (!batchId) return;
    setBusy(true);
    try {
      await cancelBatch(batchId);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [batchId, refresh]);

  const handleSaveProfile = useCallback(
    async (name: string) => {
      if (!batch) return;
      await createProfile({
        name,
        media_type: batch.media_type,
        steps: batch.steps,
      });
      setNotice(`Profile “${name}” saved.`);
    },
    [batch]
  );

  if (!batch && error) {
    return (
      <EmptyState
        glyph="!"
        title="Could not load this batch"
        body={error}
        action={
          <Link href="/">
            <Button variant="secondary">Back to home</Button>
          </Link>
        }
      />
    );
  }

  if (!batch) {
    return (
      <div className="space-y-4">
        <div className="frame-card h-24 animate-pulse" />
        <div className="frame-card h-64 animate-pulse" />
      </div>
    );
  }

  const statusTone =
    batch.status === "completed"
      ? "success"
      : batch.status === "failed"
        ? "danger"
        : batch.status === "running"
          ? "info"
          : batch.status === "cancelled"
            ? "warn"
            : "neutral";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="frame-card px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="label-caps">Processing</p>
              <Badge tone={statusTone}>{batch.status}</Badge>
              <Badge tone="info">{batch.media_type}</Badge>
            </div>
            <h1 className="mt-1 font-display text-3xl text-ink-800">
              {batch.name}
            </h1>
            <p className="mt-1 text-sm text-ink-400">
              {batch.record_count} image{batch.record_count === 1 ? "" : "s"} ·{" "}
              {batch.steps.length} step{batch.steps.length === 1 ? "" : "s"}
              {batch.profile_id && " · seeded from a profile"}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {editable && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setProfileDialogOpen(true)}
              >
                Save as profile
              </Button>
            )}
            {running ? (
              <Button variant="danger" size="sm" onClick={handleCancel} loading={busy}>
                Cancel run
              </Button>
            ) : (
              <Button
                size="sm"
                onClick={handleRun}
                loading={busy}
                disabled={!hasImages || batch.steps.length === 0}
                title={
                  !hasImages
                    ? "Upload at least one image first"
                    : batch.steps.length === 0
                      ? "This batch has no steps"
                      : "Run every step in order"
                }
              >
                Run pipeline
              </Button>
            )}
            <Link href="/gallery">
              <Button variant="ghost" size="sm">
                Gallery →
              </Button>
            </Link>
          </div>
        </div>

        {batch.error && (
          <p
            className="mt-3 rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
            role="alert"
          >
            {batch.error}
          </p>
        )}
        {actionError && (
          <p
            className="mt-3 rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
            role="alert"
          >
            {actionError}
          </p>
        )}
        {notice && !actionError && (
          <p className="mt-3 rounded-sm border border-olive-500/40 bg-olive-400/10 px-3 py-2 text-sm text-olive-400">
            {notice}
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        {/* Left: upload + results */}
        <div className="space-y-6">
          <section aria-labelledby="upload-heading">
            <h2 id="upload-heading" className="label-caps mb-2">
              Images
            </h2>
            <UploadZone
              disabled={!editable}
              onFiles={handleFiles}
              uploading={uploading}
              progress={uploadProgress}
            />
          </section>

          {batch.records.length > 0 && (
            <section aria-labelledby="images-heading" className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 id="images-heading" className="label-caps">
                  In this batch
                </h2>
                <span className="font-stamp text-[11px] text-ink-400">
                  {batch.record_count} total
                </span>
              </div>
              <RecordStrip records={batch.records} running={running} />
            </section>
          )}
        </div>

        {/* Right: the pipeline */}
        <section aria-labelledby="steps-heading" className="lg:sticky lg:top-20 lg:self-start">
          <div className="mb-2 flex items-center justify-between">
            <h2 id="steps-heading" className="label-caps">
              Pipeline
            </h2>
            {editable && (
              <span className="font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
                configure →
              </span>
            )}
          </div>
          <ol className="space-y-3">
            {batch.steps.map((step, index) => (
              <StepCard
                key={step.key}
                index={index}
                step={step}
                progress={batch.step_progress?.[step.key] ?? null}
                editable={editable}
                onConfigChange={(key, config) => void handleConfigChange(key, config)}
              />
            ))}
          </ol>

          {batch.status === "completed" && (
            <div className="frame-card mt-4 border-olive-500/60 px-4 py-3 text-center">
              <p className="font-display text-lg text-olive-400">
                Run complete ✦
              </p>
              <p className="text-sm text-ink-400">
                Results are in the gallery.
              </p>
              <Link href="/gallery">
                <Button variant="secondary" size="sm" className="mt-2">
                  Open gallery
                </Button>
              </Link>
            </div>
          )}
        </section>
      </div>

      <SaveProfileDialog
        open={profileDialogOpen}
        onClose={() => setProfileDialogOpen(false)}
        onSave={handleSaveProfile}
        mediaType={batch.media_type}
      />
    </div>
  );
}
