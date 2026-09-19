"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";

import { Banner } from "@/components/ui/Banner";
import { BucketTabs, type BucketTab } from "@/components/ui/BucketTabs";
import { PageHeader } from "@/components/ui/PageHeader";
import { StatTile, type StatTone } from "@/components/ui/StatTile";
import RecordGrid from "@/components/stages/RecordGrid";
import SelectionBar from "@/components/stages/SelectionBar";
import StageInspectModal from "@/components/stages/StageInspectModal";
import StageJobPanel from "@/components/stages/StageJobPanel";
import type { StagePageController } from "@/hooks/useStagePage";
import { resetStage, type ImageRecord } from "@/lib/api";
import { PageShell } from "@/components/shell/PageShell";
import { cn } from "@/lib/cn";
import type { BucketSpec, StageMeta } from "@/lib/stageMeta";
import { formatScore } from "@/lib/stages";

export interface StageStat {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: StatTone;
}

export interface StagePageFrameProps {
  meta: StageMeta;
  controller: StagePageController;
  /** The records this page is allowed to show, before bucket filtering. */
  pool: ImageRecord[];
  /** Bucket definitions; the first one is active on load. */
  buckets: BucketSpec[];
  /**
   * Buttons for the sticky selection bar. Receives the records currently
   * visible in the active bucket so a page can show "Scan 3 images" without
   * re-deriving the bucket filter.
   */
  renderActions: (visible: ImageRecord[]) => ReactNode;
  /** Optional readouts shown under the header. */
  stats?: StageStat[];
  /** Optional panels rendered above the grid (e.g. the upscale controls). */
  panels?: ReactNode;
  /** Copy for the empty bucket state. */
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  /** Hide the bucket strip for single-bucket pages. */
  hideBuckets?: boolean;
}

/**
 * The chrome shared by every stage page.
 *
 * Owning the buckets, the selection bar, the job panel, and the inspect modal
 * here means the seven pages only describe what makes them *different* — which
 * records they own, what their buttons say, and which panels they add.
 */
export function StagePageFrame({
  meta,
  controller,
  pool,
  buckets,
  renderActions,
  stats,
  panels,
  emptyTitle,
  emptyDescription,
  emptyAction,
  hideBuckets = false,
}: StagePageFrameProps) {
  const [activeBucketId, setActiveBucketId] = useState(buckets[0]?.id ?? "all");
  const [inspectRecord, setInspectRecord] = useState<ImageRecord | null>(null);
  const [previewVersion, setPreviewVersion] = useState(0);

  const { selection, job, error, notice, isBusy, isLoading, load } = controller;

  // Partition the pool into buckets. First match wins, so a record is counted
  // exactly once even when two buckets could claim it.
  const grouped = useMemo(() => {
    const result = new Map<string, ImageRecord[]>();
    for (const bucket of buckets) result.set(bucket.id, []);
    for (const record of pool) {
      const bucket = buckets.find((candidate) => candidate.match(record));
      if (bucket) result.get(bucket.id)?.push(record);
    }
    return result;
  }, [buckets, pool]);

  const visible = grouped.get(activeBucketId) ?? [];

  const tabs: BucketTab[] = useMemo(
    () =>
      buckets.map((bucket) => ({
        id: bucket.id,
        label: bucket.label,
        count: grouped.get(bucket.id)?.length ?? 0,
        tone: bucket.tone,
      })),
    [buckets, grouped]
  );

  const activeBucket = buckets.find((bucket) => bucket.id === activeBucketId);

  // Keep the inspected record in sync with polling refreshes.
  useEffect(() => {
    if (!inspectRecord) return;
    const refreshed = pool.find((record) => record.id === inspectRecord.id);
    if (refreshed && refreshed !== inspectRecord) setInspectRecord(refreshed);
  }, [pool, inspectRecord]);

  // Drop selections whose records left this page's pool.
  const poolIds = useMemo(() => pool.map((record) => record.id), [pool]);
  const { prune } = selection;
  useEffect(() => {
    prune(poolIds);
  }, [poolIds, prune]);

  // Auto-dismiss transient notices.
  const clearNotice = controller.clearNotice;
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(clearNotice, 5000);
    return () => clearTimeout(timer);
  }, [notice, clearNotice]);

  // Force previews to refetch whenever a batch finishes.
  const jobStatus = job?.status;
  useEffect(() => {
    if (jobStatus && jobStatus !== "running") setPreviewVersion(Date.now());
  }, [jobStatus]);

  // A selection made in one bucket is meaningless in another.
  const { clear } = selection;
  useEffect(() => {
    clear();
  }, [activeBucketId, clear]);

  const allVisibleSelected =
    visible.length > 0 && visible.every((record) => selection.isSelected(record.id));

  const runningIds = useMemo(
    () => (isBusy && job ? job.items.map((item) => item.record_id) : []),
    [isBusy, job]
  );

  async function handleReset(record: ImageRecord) {
    try {
      await resetStage(record.id);
      setInspectRecord(null);
      await load();
    } catch (err) {
      controller.setError(
        err instanceof Error ? err.message : "Could not reset the record."
      );
    }
  }

  return (
    <PageShell>
      <PageHeader
        step={meta.number}
        title={meta.name}
        tagline={meta.tagline}
        icon={<meta.icon className="h-5 w-5" aria-hidden />}
        actions={
          <button
            type="button"
            onClick={() => void load(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-navy-700/60 px-3 py-1.5 text-xs font-medium text-navy-200 transition-colors hover:bg-navy-750/60 hover:text-navy-50"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} aria-hidden />
            Refresh
          </button>
        }
      />

      {stats && stats.length > 0 ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
          {stats.map((stat) => (
            <StatTile
              key={stat.label}
              label={stat.label}
              value={stat.value}
              hint={stat.hint}
              tone={stat.tone}
            />
          ))}
        </div>
      ) : null}

      {error ? (
        <Banner tone="error" onDismiss={() => controller.setError(null)}>
          {error}
        </Banner>
      ) : null}

      {notice ? (
        <Banner tone="success" onDismiss={clearNotice}>
          {notice}
        </Banner>
      ) : null}

      {panels}

      {job ? (
        <StageJobPanel
          job={job}
          onCancel={() => void controller.stopJob()}
          onDismiss={controller.clearJob}
        />
      ) : null}

      {!hideBuckets ? (
        <div className="space-y-3">
          <BucketTabs tabs={tabs} activeId={activeBucketId} onChange={setActiveBucketId} />
          {activeBucket ? (
            <p className="text-xs text-navy-400">{activeBucket.hint}</p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-3">
        <SelectionBar
          totalCount={visible.length}
          selectedCount={selection.count}
          isAllSelected={allVisibleSelected}
          onSelectAll={() => selection.selectMany(visible.map((record) => record.id))}
          onClearSelection={selection.clear}
          actionsDisabled={isBusy || isLoading}
        >
          {renderActions(visible)}
        </SelectionBar>

        <RecordGrid
          records={visible}
          isLoading={isLoading}
          isSelected={selection.isSelected}
          onToggleSelect={selection.toggle}
          onInspect={setInspectRecord}
          runningIds={runningIds}
          emptyTitle={emptyTitle ?? `Nothing in ${activeBucket?.label ?? "this bucket"}`}
          emptyDescription={emptyDescription ?? activeBucket?.hint}
          emptyAction={emptyAction}
        />
      </div>

      <StageInspectModal
        record={inspectRecord}
        isOpen={inspectRecord !== null}
        isBusy={isBusy}
        onClose={() => setInspectRecord(null)}
        onReset={handleReset}
        onFixed={() => void load()}
        previewVersion={previewVersion}
      />
    </PageShell>
  );
}

/** Average acceptance score across a record pool, or null when unscored. */
export function averageScore(records: ImageRecord[]): string {
  const scored = records.filter(
    (record) => typeof record.acceptance_score === "number"
  );
  if (scored.length === 0) return "—";
  const total = scored.reduce((sum, record) => sum + (record.acceptance_score ?? 0), 0);
  return formatScore(total / scored.length);
}

export default StagePageFrame;
