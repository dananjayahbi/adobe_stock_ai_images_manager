/** Typed API client for image records (home + gallery). */
import { api } from "./client";
import type { ImageRecord } from "./types";

export interface RecordPage {
  items: ImageRecord[];
  total: number;
  page: number;
  page_size: number;
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
  search?: string;
  stageUpdated?: boolean;
}): Promise<RecordPage> {
  const { data } = await api.get("/api/records", {
    params: {
      limit: options.limit ?? 100,
      offset: options.offset ?? 0,
      ...(options.search ? { search: options.search } : {}),
      ...(options.stageUpdated ? { stage_updated: "true" } : {}),
    },
  });
  return data;
}
