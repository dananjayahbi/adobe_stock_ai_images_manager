/** Typed API client for image records (home + gallery). */
import { api } from "./client";
import type { ImageLifecycleState, ImageRecord } from "./types";

export interface RecordPage {
  items: ImageRecord[];
  total: number;
  page: number;
  page_size: number;
}

/** Gallery filters. All are image-level — groups are never filtered. */
export interface RecordFilters {
  search?: string;
  stage?: string;
  /** Comma-separated lifecycle states (backend `state=A,B`, like `stage=`). */
  state?: string;
  used?: "all" | "used" | "unused";
  /** A group id, or "none" for ungrouped images. */
  groupId?: string;
}

/**
 * Fetch processed records.
 *
 * `stageUpdated` scopes to images a pipeline has actually touched (the home
 * page's "latest processed"); without it the gallery shows everything.
 */
export async function fetchRecords(options: {
  limit?: number;
  offset?: number;
  stageUpdated?: boolean;
} & RecordFilters): Promise<RecordPage> {
  const { data } = await api.get("/api/records", {
    params: {
      limit: options.limit ?? 100,
      offset: options.offset ?? 0,
      ...(options.search ? { search: options.search } : {}),
      ...(options.stage ? { stage: options.stage } : {}),
      ...(options.state ? { state: options.state } : {}),
      ...(options.used && options.used !== "all" ? { used: options.used } : {}),
      ...(options.groupId ? { group_id: options.groupId } : {}),
      ...(options.stageUpdated ? { stage_updated: "true" } : {}),
    },
  });
  return data;
}

/** Delete records and their on-disk artifacts (gallery multi-delete). */
export async function deleteRecords(recordIds: string[]): Promise<{ deleted: number }> {
  const { data } = await api.post("/api/records/bulk-delete", {
    record_ids: recordIds,
  });
  return data;
}

/**
 * Mark records as used/unused in one transaction (gallery multi-select).
 *
 * `used_at` is the backend's bookkeeping: set when marking used, cleared when
 * marking unused — the client only decides the flag.
 */
export async function setRecordsUsed(
  recordIds: string[],
  isUsed: boolean
): Promise<{ updated: number; missing?: string[] }> {
  const { data } = await api.patch("/api/records/used", {
    record_ids: recordIds,
    is_used: isUsed,
  });
  return data;
}

/**
 * Move one record through the lifecycle (`PATCH /api/records/{id}/state`).
 *
 * Returns the full updated record on 200; the backend answers 400 with a
 * `detail` string for a disallowed transition (the client normalises that
 * into an `Error`), which the caller surfaces inline.
 */
export async function changeRecordState(
  id: string,
  state: ImageLifecycleState
): Promise<ImageRecord> {
  const { data } = await api.patch(`/api/records/${id}/state`, { state });
  return data;
}

/**
 * Fast approve (`POST /api/records/{id}/approve`) — flips APPROVED|REJECTED
 * to READY_TO_PUBLISH without running any LLM step.
 */
export async function approveRecord(id: string): Promise<ImageRecord> {
  const { data } = await api.post(`/api/records/${id}/approve`);
  return data;
}
