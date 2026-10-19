/** API client for the gallery's manual "push to ready-to-upload" override. */
import { api } from "./client";

/** One requirement's state for one record. */
export interface PromoteStep {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

/** Pre-flight report for a single record. */
export interface PromoteCheckItem {
  record_id: string;
  filename: string;
  stage: string;
  eligible: boolean;
  blocker: string | null;
  steps: PromoteStep[];
}

export interface PromoteCheckResponse {
  items: PromoteCheckItem[];
  missing: string[];
}

/**
 * Pre-flight: which of the three requirements (acceptance QC, sRGB profile,
 * metadata) each record is missing. Nothing is executed or written.
 */
export async function checkPromote(
  recordIds: string[]
): Promise<PromoteCheckResponse> {
  const { data } = await api.post("/api/promote/check", {
    record_ids: recordIds,
  });
  return data;
}

/** One item's state inside a promote job (mirrors the backend JobItem). */
export interface PromoteJobItem {
  record_id: string;
  filename: string;
  status: string;
  message: string;
  score: number | null;
}

/** A running/finished promote job (subset of the backend JobResponse). */
export interface PromoteJob {
  id: string;
  status: string;
  message: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  skipped: number;
  progress: number;
  items: PromoteJobItem[];
}

/**
 * Run the missing steps per record and promote the ones that end up passing.
 *
 * Returns the job handle; poll [`fetchPromoteJob`] until it completes.
 */
export async function runPromote(
  recordIds: string[],
  useSemantic = false
): Promise<PromoteJob> {
  const { data } = await api.post("/api/promote/run", {
    record_ids: recordIds,
    use_semantic: useSemantic,
  });
  return data;
}

/** Poll a promote job's progress. */
export async function fetchPromoteJob(jobId: string): Promise<PromoteJob> {
  const { data } = await api.get(`/api/jobs/${jobId}`);
  return data;
}
