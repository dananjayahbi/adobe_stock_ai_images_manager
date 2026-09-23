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
  /**
   * Optional readouts shown under the header.
   *
   * The Collector deliberately passes none: it is a two-pane workspace, and a
   * row of metric cards between the header and the split pushed the gallery
   * down for numbers the operator can already see in the buckets.
   */
  stats?: StageStat[];
  /**
   * Panels rendered above the buckets inside the gallery pane.
   *
   * Used by stages whose run needs configuration (the Upscale options). They
   * sit *inside* the left column so nothing can stack above the split.
   */
  panels?: ReactNode;
  /**
   * A tile pinned to the **first cell of the record grid**.
   *
   * The Collector uses this for its upload slot. It is a grid cell rather than
   * a stacked panel because the place images arrive belongs among the images.
   */
  gridLeadingSlot?: ReactNode;
  /**
   * Right-hand pane, rendered beside the gallery at a fixed 1/3 of the width.
   *
   * The Collector uses this for the Prompt Library: the prompts are the
   * *source* of the collected images, so the two belong side by side. When
   * omitted the page stays single-column.
   */
  sidePanel?: ReactNode;
  /**
   * Controls rendered inside the page header, beside the title.
   *
   * The Collector puts its mode switcher here so it reads as page chrome
   * rather than a band of content competing with the gallery.
   */
  headerExtra?: ReactNode;
  /**
   * Prompt binding passthrough for the grid. Only the Collector supplies these;
   * every other stage leaves them undefined and the tiles stay plain.
   */
  onPromptDrop?: (recordId: string, promptId: string) => void;
  promptTitleFor?: (record: ImageRecord) => string | null;
  /** Copy for the empty bucket state. */
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: ReactNode;
  /** Hide the bucket strip for single-bucket pages. */
  hideBuckets?: boolean;
  /**
   * Optional overrides for the banner slots.
   *
   * A page that owns a second state source (the Collector's Prompt Library)
   * merges its messages into one banner here instead of rendering two, which
   * would stack duplicate "something failed" strips.
   */
  error?: string | null;
  notice?: string | null;
  onClearError?: () => void;
  onClearNotice?: () => void;
}

/**
 * The split ratio: the gallery takes two thirds, the side pane one third.
 *
 * Expressed as `fr` tracks with `minmax(0, …)` so a wide image grid cannot
 * force the side pane narrower than its share.
 */
const SPLIT_COLUMNS = "xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]";

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
  gridLeadingSlot,
  sidePanel,
  headerExtra,
  onPromptDrop,
  promptTitleFor,
  emptyTitle,
  emptyDescription,
  emptyAction,
  hideBuckets = false,
  error: errorOverride,
  notice: noticeOverride,
  onClearError,
  onClearNotice,
}: StagePageFrameProps) {
  const [activeBucketId, setActiveBucketId] = useState(buckets[0]?.id ?? "all");
  const [inspectRecord, setInspectRecord] = useState<ImageRecord | null>(null);
  const [previewVersion, setPreviewVersion] = useState(0);

  const { selection, job, isLoading, load } = controller;

  // A page may supply its own error/notice (and its own dismiss handler) when it
  // merges in a second state source; otherwise the controller's are used.
  const error = errorOverride !== undefined ? errorOverride : controller.error;
  const notice = noticeOverride !== undefined ? noticeOverride : controller.notice;
  const clearNotice = onClearNotice ?? controller.clearNotice;
  const clearError = onClearError ?? (() => controller.setError(null));
  const isBusy = controller.isBusy;

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
          <div className="flex flex-wrap items-center gap-2">
            {headerExtra}
            <button
              type="button"
              onClick={() => void load(true)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-navy-700/60 px-3 py-1.5 text-xs font-medium text-navy-200 transition-colors hover:bg-navy-750/60 hover:text-navy-50"
            >
              <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} aria-hidden />
              Refresh
            </button>
          </div>
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
        <Banner tone="error" onDismiss={clearError}>
          {error}
        </Banner>
      ) : null}

      {notice ? (
        <Banner tone="success" onDismiss={clearNotice}>
          {notice}
        </Banner>
      ) : null}

      {job ? (
        <StageJobPanel
          job={job}
          onCancel={() => void controller.stopJob()}
          onDismiss={controller.clearJob}
        />
      ) : null}

      {/*
        * The split *is* the page body: gallery (2/3) on the left, the page's
        * side pane (1/3) on the right. Everything belonging to the gallery —
        * its controls, buckets, selection bar and grid — lives inside the left
        * column, so nothing can stack above the split and break the columns.
        */}
      <div
        className={cn(
          "space-y-3",
          sidePanel != null && cn("xl:grid xl:gap-6 xl:space-y-0", SPLIT_COLUMNS)
        )}
      >
        <div className="min-w-0 space-y-3">
          {panels}

          {!hideBuckets ? (
            <div className="space-y-3">
              <BucketTabs
                tabs={tabs}
                activeId={activeBucketId}
                onChange={setActiveBucketId}
              />
              {activeBucket ? (
                <p className="text-xs text-navy-400">{activeBucket.hint}</p>
              ) : null}
            </div>
          ) : null}

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
            onPromptDrop={onPromptDrop}
            promptTitleFor={promptTitleFor}
            leadingSlot={gridLeadingSlot}
            emptyTitle={emptyTitle ?? `Nothing in ${activeBucket?.label ?? "this bucket"}`}
            emptyDescription={emptyDescription ?? activeBucket?.hint}
            emptyAction={emptyAction}
          />
        </div>

        {sidePanel != null ? (
          // Sticky on large screens so the prompt library stays reachable while
          // the operator scrolls a long collection grid.
          <div className="min-w-0 xl:sticky xl:top-[57px] xl:max-h-[calc(100vh-5rem)]">
            {sidePanel}
          </div>
        ) : null}
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

export default StagePageFrame;
