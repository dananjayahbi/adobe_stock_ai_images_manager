/** Typed API client for image records (home + gallery). */
import { api } from "./client";
import type { ImageRecord } from "./types";

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
