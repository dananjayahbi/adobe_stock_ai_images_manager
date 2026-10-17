/** Typed API client for batches (batch pipeline v2). */
import { api } from "./client";
import type {
  Batch,
  BatchDetail,
  BatchStep,
  MediaType,
  StepCatalog,
  UploadResult,
} from "./types";

export async function fetchStepCatalog(mediaType?: MediaType): Promise<StepCatalog> {
  const { data } = await api.get("/api/batches/steps", {
    params: mediaType ? { media_type: mediaType } : {},
  });
  return data;
}

export async function listBatches(
  limit = 50
): Promise<{ items: Batch[]; total: number }> {
  const { data } = await api.get("/api/batches", { params: { limit } });
  return data;
}

export async function createBatch(payload: {
  name?: string;
  media_type: MediaType;
  steps?: BatchStep[];
  profile_id?: string;
}): Promise<Batch> {
  const { data } = await api.post("/api/batches", payload);
  return data;
}

export async function fetchBatch(id: string): Promise<BatchDetail> {
  const { data } = await api.get(`/api/batches/${id}`);
  return data;
}

export async function updateBatch(
  id: string,
  payload: { name?: string; steps?: BatchStep[] }
): Promise<Batch> {
  const { data } = await api.patch(`/api/batches/${id}`, payload);
  return data;
}

export async function deleteBatch(id: string): Promise<{ deleted: string }> {
  const { data } = await api.delete(`/api/batches/${id}`);
  return data;
}

export async function uploadToBatch(
  id: string,
  files: File[],
  onProgress?: (percent: number) => void
): Promise<UploadResult> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const { data } = await api.post(`/api/batches/${id}/files`, form, {
    timeout: 300_000,
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    },
  });
  return data;
}

export async function runBatch(id: string): Promise<Batch> {
  const { data } = await api.post(`/api/batches/${id}/run`);
  return data;
}

/**
 * Enqueue a batch explicitly. Since the server queues runs serially, `/queue`
 * and `/run` are the same enqueue call — Run is just the friendlier name for
 * the first click, Queue for "get in line behind whatever is running".
 */
export async function queueBatch(id: string): Promise<Batch> {
  const { data } = await api.post(`/api/batches/${id}/queue`);
  return data;
}

export async function cancelBatch(id: string): Promise<Batch> {
  const { data } = await api.post(`/api/batches/${id}/cancel`);
  return data;
}
