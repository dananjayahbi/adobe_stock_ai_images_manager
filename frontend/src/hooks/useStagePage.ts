"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  cancelJob,
  deleteRecord,
  deleteRecords,
  fetchJob,
  fetchRecords,
  fetchStageSummary,
  pushToQueue,
  removeFromQueue,
  runStage,
  type ImageRecord,
} from "@/lib/api";
import type { StageJob, StageSummary } from "@/lib/stages";
import type { UpscaleOptions } from "@/lib/upscale";

import { useRecordSelection } from "./useRecordSelection";

const POLL_INTERVAL_MS = 4000;
const PAGE_LIMIT = 500;
const JOB_POLL_INTERVAL_MS = 1500;

export interface RunStageArgs {
  stageKey: string;
  recordIds: string[];
  delaySeconds?: number;
  useSemantic?: boolean;
  upscale?: Partial<UpscaleOptions>;
}

/**
 * Data + actions for a single stage page.
 *
 * One hook serves all seven pages so the behaviour (polling, job lifecycle,
 * queue push, deletion) is identical everywhere. Page components only decide
 * how to *render* the records they are given.
 *
 * Records are fetched once and partitioned client-side. The API filters by
 * `status`, not `stage`, so partitioning here keeps the backend contract
 * unchanged while letting a page show drafts and verdicts side by side.
 */
export function useStagePage() {
  const [records, setRecords] = useState<ImageRecord[]>([]);
  const [summary, setSummary] = useState<StageSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPushing, setIsPushing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [job, setJob] = useState<StageJob | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const requestId = useRef(0);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const selection = useRecordSelection();

  const load = useCallback(async (showSpinner = false) => {
    const id = ++requestId.current;
    if (showSpinner) setIsLoading(true);

    try {
      const [listing, stageSummary] = await Promise.all([
        fetchRecords({ limit: PAGE_LIMIT }),
        fetchStageSummary(),
      ]);
      if (id !== requestId.current) return;
      setRecords(listing.items);
      setSummary(stageSummary);
      setError(null);
    } catch (err) {
      if (id !== requestId.current) return;
      setError(err instanceof Error ? err.message : "Failed to load records.");
    } finally {
      if (id === requestId.current && showSpinner) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    const interval = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [load]);

  const stopJobPolling = useCallback(() => {
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }
  }, []);

  useEffect(() => stopJobPolling, [stopJobPolling]);

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
          // A transient poll failure must not abort the batch.
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
        const started = await runStage(stageKey as never, recordIds, {
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

  /** Move records into another stage's queue — the "push" action. */
  const push = useCallback(
    async (stageKey: string, ids: string[]) => {
      if (ids.length === 0) {
        setError("Select at least one image to push.");
        return;
      }
      setIsPushing(true);
      setError(null);
      setNotice(null);
      try {
        const result = await pushToQueue(stageKey as never, ids);
        selection.clear();
        await load();
        setNotice(`Pushed ${result.updated} image(s) onward.`);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not push the selection.");
      } finally {
        setIsPushing(false);
      }
    },
    [load, selection]
  );

  /** Pull records back out of this stage's queue. */
  const unpush = useCallback(
    async (stageKey: string, ids: string[]) => {
      if (ids.length === 0) return;
      setIsPushing(true);
      setError(null);
      try {
        await removeFromQueue(stageKey as never, ids);
        selection.clear();
        await load();
        setNotice("Removed from the queue.");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not update the queue.");
      } finally {
        setIsPushing(false);
      }
    },
    [load, selection]
  );

  const removeRecords = useCallback(
    async (ids: string[]) => {
      if (ids.length === 0) return;
      if (ids.length === 1) await deleteRecord(ids[0]);
      else await deleteRecords(ids);
      selection.clear();
      await load();
    },
    [load, selection]
  );

  const counts = useMemo(() => {
    const map: Partial<Record<string, number>> = {};
    for (const entry of summary?.counts ?? []) {
      map[entry.stage] = entry.count;
    }
    return map;
  }, [summary]);

  return {
    records,
    summary,
    counts,
    isLoading,
    isBusy,
    isPushing,
    error,
    notice,
    job,
    selection,
    setError,
    clearNotice,
    clearJob,
    load,
    startStage,
    stopJob,
    push,
    unpush,
    removeRecords,
  };
}

export type StagePageController = ReturnType<typeof useStagePage>;
