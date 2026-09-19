"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  cancelJob,
  deleteRecord,
  deleteRecords,
  fetchJob,
  fetchRecords,
  fetchStageSummary,
  runStage,
  type ImageRecord,
} from "@/lib/api";
import {
  STAGE_ENTRY_STAGES,
  isTerminalStage,
  type PipelineStage,
  type StageKey,
  type StageJob,
  type StageSummary,
} from "@/lib/stages";
import type { UpscaleOptions } from "@/lib/upscale";

const POLL_INTERVAL_MS = 4000;
const PAGE_LIMIT = 500;

/** How often to poll a running batch job. Batches are long, so this is relaxed. */
const JOB_POLL_INTERVAL_MS = 1500;

export interface RunStageArgs {
  stageKey: StageKey;
  recordIds: string[];
  delaySeconds?: number;
  useSemantic?: boolean;
  /** Stage 3 only: the operator's upscaler settings. */
  upscale?: Partial<UpscaleOptions>;
}

/**
 * Owns the stage workspace's data: the record list for the active stage, the
 * per-stage counts, and the lifecycle of a running batch job.
 *
 * The record list is deliberately scoped to *one* stage at a time. Every stage
 * action is a batch over the visible selection, so loading all 500 records and
 * filtering client-side would make the "select all" affordance ambiguous.
 */
export function useStageRecords() {
  const [activeStage, setActiveStage] = useState<PipelineStage>("COLLECTED");
  const [records, setRecords] = useState<ImageRecord[]>([]);
  const [summary, setSummary] = useState<StageSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [job, setJob] = useState<StageJob | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  // Monotonic request id: only the newest response is applied, so a stage
  // switch during a poll is never silently discarded.
  const requestId = useRef(0);
  const stageRef = useRef<PipelineStage>(activeStage);
  stageRef.current = activeStage;
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (showSpinner = false) => {
    const id = ++requestId.current;
    if (showSpinner) setIsLoading(true);

    try {
      const [listing, stageSummary] = await Promise.all([
        fetchRecords({ status: undefined, limit: PAGE_LIMIT }),
        fetchStageSummary(),
      ]);
      if (id !== requestId.current) return;

      // The API filters by `status`, not `stage`, so the stage filter is
      // applied here. This keeps the backend contract unchanged.
      setRecords(listing.items.filter((r) => r.stage === stageRef.current));
      setSummary(stageSummary);
      setError(null);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : "Failed to load the pipeline.");
    } finally {
      if (id === requestId.current && showSpinner) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load, activeStage]);

  useEffect(() => {
    const interval = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  // Stop polling a job once it reaches a terminal state.
  const stopJobPolling = useCallback(() => {
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }
  }, []);

  useEffect(() => stopJobPolling, [stopJobPolling]);

  /**
   * Poll a job until it finishes.
   *
   * The interval is owned by a ref rather than an effect dep so that starting a
   * second batch cancels the first poller instead of leaking it.
   */
  const pollJob = useCallback(
    (jobId: string) => {
      stopJobPolling();

      const tick = async () => {
        try {
          const latest = await fetchJob(jobId);
          setJob(latest);

          if (latest.status !== "running") {
            stopJobPolling();
            setIsBusy(false);
            await load();

            const parts = [`${latest.succeeded} succeeded`];
            if (latest.failed) parts.push(`${latest.failed} failed`);
            if (latest.skipped) parts.push(`${latest.skipped} skipped`);
            setNotice(`${latest.kind} finished · ${parts.join(" · ")}`);
          }
        } catch (err) {
          // A transient poll failure should not abort the batch; keep polling
          // and surface the error without clearing the job view.
          setError(err instanceof Error ? err.message : "Lost contact with the job.");
        }
      };

      void tick();
      jobPollRef.current = setInterval(() => void tick(), JOB_POLL_INTERVAL_MS);
    },
    [load, stopJobPolling]
  );

  const startStage = useCallback(
    async ({ stageKey, recordIds, delaySeconds, useSemantic, upscale }: RunStageArgs) => {
      if (recordIds.length === 0) {
        setError("Select at least one image first.");
        return;
      }

      setIsBusy(true);
      setError(null);
      setNotice(null);

      try {
        const started = await runStage(stageKey, recordIds, {
          delaySeconds,
          useSemantic,
          upscale,
        });
        setJob(started);
        pollJob(started.id);
      } catch (err) {
        setIsBusy(false);
        setError(err instanceof Error ? err.message : "Could not start the stage.");
      }
    },
    [pollJob]
  );

  /**
   * Permanently remove records, from any stage.
   *
   * The server drops the inbox original, the thumbnail, and every staged copy,
   * so the caller only has to refresh. Deleting a running record is refused by
   * the UI, not here - the batch may still hold the file open.
   */
  const removeRecords = useCallback(
    async (ids: string[]) => {
      if (ids.length === 0) return;
      if (ids.length === 1) await deleteRecord(ids[0]);
      else await deleteRecords(ids);
      await load();
    },
    [load]
  );

  const stopJob = useCallback(async () => {
    if (!job || job.status !== "running") return;
    try {
      const updated = await cancelJob(job.id);
      setJob(updated);
      setNotice("Cancellation requested; the batch stops after the current image.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel the job.");
    }
  }, [job]);

  const clearJob = useCallback(() => {
    stopJobPolling();
    setJob(null);
    setIsBusy(false);
  }, [stopJobPolling]);

  const clearNotice = useCallback(() => setNotice(null), []);

  /** Records in this stage that the given stage key can act on. */
  const eligibleFor = useCallback(
    (stageKey: StageKey): ImageRecord[] => {
      const entryStages = STAGE_ENTRY_STAGES[stageKey];
      return records.filter((record) => entryStages.includes(record.stage));
    },
    [records]
  );

  const counts = useMemo(() => {
    const map: Partial<Record<PipelineStage, number>> = {};
    for (const entry of summary?.counts ?? []) {
      map[entry.stage] = entry.count;
    }
    return map;
  }, [summary]);

  return {
    activeStage,
    setActiveStage,
    records,
    counts,
    summary,
    isLoading,
    isBusy,
    error,
    notice,
    job,
    setError,
    clearNotice,
    clearJob,
    load,
    startStage,
    stopJob,
    removeRecords,
    eligibleFor,
    isTerminal: isTerminalStage(activeStage),
  };
}
