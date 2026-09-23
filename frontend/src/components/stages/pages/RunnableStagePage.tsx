"use client";

import { ArrowRight, Play, RotateCcw } from "lucide-react";
import { useMemo, type ReactNode } from "react";

import StageDeleteButton from "@/components/stages/StageDeleteButton";
import StagePageFrame, { type StageStat } from "@/components/stages/pages/StagePageFrame";
import { Button } from "@/components/ui/Button";
import { useStagePage } from "@/hooks/useStagePage";
import type { ImageRecord } from "@/lib/api";
import { STAGE_META, poolFor, type StageMeta } from "@/lib/stageMeta";
import type { StageKey } from "@/lib/stages";
import type { UpscaleOptions } from "@/lib/upscale";

export interface RunnableStagePageProps {
  stageKey: StageKey;
  /** Extra buttons for the selection bar, rendered before the standard ones. */
  extraActions?: (selected: ImageRecord[]) => ReactNode;
  /** Panels rendered above the grid. */
  panels?: ReactNode;
  /** Replace the default stat tiles. */
  stats?: StageStat[];
  /**
   * Run options forwarded to `POST /api/stages/{key}/run`.
   *
   * Upscale needs its own configuration, so the page supplies it here.
   */
  runOptions?: { delaySeconds?: number; upscale?: Partial<UpscaleOptions> };
  /** Label for the primary run button; defaults to the stage's action copy. */
  actionLabel?: string;
  /** Hide the primary run button entirely (e.g. a review-only page). */
  hideRun?: boolean;
  /** Called after a run finishes, e.g. to refresh a derived preview. */
  onRan?: () => void;
  /** Copy shown in an empty bucket. */
  emptyDescription?: string;
  /**
   * Optional overrides for the page's message banner.
   *
   * A page that owns a second state source (the Compatibility page's manual
   * override) merges its messages into the one existing banner instead of
   * stacking a duplicate strip beneath it.
   */
  error?: string | null;
  notice?: string | null;
  onClearError?: () => void;
  onClearNotice?: () => void;
}

/**
 * The shared body of every *runnable* stage page.
 *
 * Each page differs only in which records it owns, what extra panels it shows,
 * and whether its run needs configuration — so those are the only props. The
 * standard action set (run, push onward, delete) is defined once here, which is
 * what keeps the seven pages consistent as the pipeline grows.
 */
export function RunnableStagePage({
  stageKey,
  extraActions,
  panels,
  stats,
  runOptions,
  actionLabel,
  hideRun = false,
  onRan,
  emptyDescription,
  error,
  notice,
  onClearError,
  onClearNotice,
}: RunnableStagePageProps) {
  const controller = useStagePage();
  const { records, push, removeRecords, startStage, isBusy, isPushing, selection } =
    controller;

  const meta: StageMeta = STAGE_META[stageKey];
  const pool = useMemo(() => poolFor(records, stageKey), [records, stageKey]);

  const defaultStats: StageStat[] = useMemo(() => {
    const draft = pool.filter((record) => record.queued_stage === stageKey).length;
    const processed = pool.filter((record) => record.queued_stage !== stageKey).length;

    return [
      { label: "Draft", value: draft, hint: "Not processed yet", tone: "accent" },
      { label: "Processed", value: processed, hint: "Ready to move on", tone: "success" },
      { label: "Total", value: pool.length },
    ];
  }, [pool, stageKey]);

  return (
    <StagePageFrame
      meta={meta}
      controller={controller}
      pool={pool}
      buckets={meta.buckets}
      stats={stats ?? defaultStats}
      panels={panels}
      emptyTitle="Nothing in this bucket"
      emptyDescription={
        emptyDescription ?? "Push images here from the previous stage to get started."
      }
      error={error}
      notice={notice}
      onClearError={onClearError}
      onClearNotice={onClearNotice}
      renderActions={(visible) => {
        const selected = visible.filter((record) => selection.isSelected(record.id));
        const ids = selected.map((record) => record.id);
        const hasDrafts = selected.some((record) => record.queued_stage === stageKey);
        const processedIds = selected
          .filter((record) => record.queued_stage !== stageKey)
          .map((record) => record.id);

        return (
          <>
            {extraActions?.(selected)}

            {!hideRun && hasDrafts ? (
              <Button
                size="sm"
                variant="primary"
                disabled={isBusy}
                isLoading={isBusy}
                onClick={() => {
                  void startStage({ stageKey, recordIds: ids, ...runOptions });
                  onRan?.();
                }}
                icon={isBusy ? undefined : <Play className="h-3.5 w-3.5" aria-hidden />}
              >
                {actionLabel ?? meta.action} ({selected.length})
              </Button>
            ) : null}

            {meta.next && processedIds.length > 0 ? (
              <Button
                size="sm"
                variant="secondary"
                disabled={isPushing}
                onClick={() => void push(meta.next as StageKey, processedIds)}
                icon={<ArrowRight className="h-3.5 w-3.5" aria-hidden />}
              >
                {meta.pushLabel} ({processedIds.length})
              </Button>
            ) : null}

            {!hideRun && processedIds.length > 0 ? (
              <Button
                size="sm"
                variant="ghost"
                disabled={isBusy}
                onClick={() =>
                  void startStage({ stageKey, recordIds: processedIds, ...runOptions })
                }
                icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
              >
                Re-run
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
  );
}

export default RunnableStagePage;
