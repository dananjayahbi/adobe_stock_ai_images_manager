import axios from "axios";

import type {
  AcceptanceReport,
  AdobeCategory,
  CsvPreview,
  PipelineStage,
  StageDefinition,
  StageDetails,
  StageJob,
  StageKey,
  StageSummary,
} from "./stages";
import type { UpscaleOptions } from "./upscale";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8100";

export type ImageStatus =
  | "PENDING"
  | "AUDITING"
  | "PASSED"
  | "FLAGGED"
  | "APPROVED"
  | "READY";

export interface ImageRecord {
  id: string;
  filename: string;
  original_path: string;
  thumbnail_path: string | null;
  status: ImageStatus;
  width: number | null;
  height: number | null;
  megapixels: number | null;
  file_size_bytes: number;
  laplacian_variance: number | null;
  ocr_text_detected: boolean;
  ocr_text_content: string | null;
  semantic_confidence_score: number | null;
  semantic_flags: string[] | Record<string, unknown> | null;
  generated_title: string | null;
  generated_description: string | null;
  generated_keywords: string[] | null;
  is_used: boolean;
  used_at: string | null;
  created_at: string;
  updated_at: string;

  // Stage pipeline
  stage: PipelineStage;
  /**
   * Stage key this record has been pushed into, awaiting a run.
   * `null` means the record is not queued anywhere.
   */
  queued_stage: StageKey | null;
  working_path: string | null;
  stage_updated_at: string | null;
  acceptance_report: AcceptanceReport | null;
  acceptance_score: number | null;
  refine_passes: number;
  stage_details: StageDetails | null;
  category: number | null;
}

export interface RecordListResponse {
  items: ImageRecord[];
  total: number;
  page: number;
  page_size: number;
}

export interface UploadResponse {
  record_ids: string[];
  count: number;
}

export interface ApproveResponse {
  record_id: string;
  status: ImageStatus;
  title: string | null;
  keywords_count: number;
}

export interface ApproveOverrides {
  override_title?: string;
  override_description?: string;
  override_keywords?: string[];
}

export type UsageFilter = "all" | "unused" | "used";

export interface BulkActionResult {
  updated: number;
  deleted: number;
  missing: string[];
  failed: string[];
}

export interface UploadTableItem {
  record_id: string;
  filename: string;
  title: string;
  description: string;
  keywords: string[];
  keywords_csv: string;
  thumbnail_url: string | null;
  download_url: string;
}

export interface UploadTableResponse {
  items: UploadTableItem[];
  missing: string[];
}

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail =
      error?.response?.data?.detail ??
      error?.message ??
      "Unexpected network error.";
    return Promise.reject(new Error(String(detail)));
  }
);

export async function uploadImages(
  files: File[],
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  for (const file of files) {
    formData.append("files", file);
  }
  const { data } = await api.post<UploadResponse>("/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total));
      }
    },
  });
  return data;
}

export async function fetchRecords(params?: {
  status?: ImageStatus;
  used?: UsageFilter;
  /** Stage key to filter by pending queue, or "none" for unqueued records. */
  queued?: StageKey | "none";
  ids?: string[];
  limit?: number;
  offset?: number;
}): Promise<RecordListResponse> {
  const { ids, ...rest } = params ?? {};
  const { data } = await api.get<RecordListResponse>("/api/records", {
    params: { ...rest, ids: ids && ids.length > 0 ? ids.join(",") : undefined },
  });
  return data;
}

/**
 * Push records into a stage's queue without running it.
 *
 * The push records *intent*: the destination page lists these records in its
 * draft bucket until the operator runs the stage there.
 */
export async function pushToQueue(
  stageKey: StageKey,
  recordIds: string[]
): Promise<BulkActionResult> {
  const { data } = await api.post<BulkActionResult>(
    `/api/queues/${stageKey}/push`,
    { record_ids: recordIds }
  );
  return data;
}

/** Clear the queue entry for records that should no longer be pushed. */
export async function removeFromQueue(
  stageKey: StageKey,
  recordIds: string[]
): Promise<BulkActionResult> {
  const { data } = await api.post<BulkActionResult>(
    `/api/queues/${stageKey}/remove`,
    { record_ids: recordIds }
  );
  return data;
}

/** Pending queue depth per stage key. */
export interface QueueSummary {
  counts: Record<string, number>;
  total: number;
}

export async function fetchQueueSummary(): Promise<QueueSummary> {
  const { data } = await api.get<QueueSummary>("/api/queues/summary");
  return data;
}

export async function fetchRecord(id: string): Promise<ImageRecord> {
  const { data } = await api.get<ImageRecord>(`/api/records/${id}`);
  return data;
}

export async function setRecordUsed(
  id: string,
  isUsed: boolean
): Promise<BulkActionResult> {
  const { data } = await api.patch<BulkActionResult>(`/api/records/${id}/used`, {
    is_used: isUsed,
  });
  return data;
}

export async function setRecordsUsed(
  ids: string[],
  isUsed: boolean
): Promise<BulkActionResult> {
  const { data } = await api.patch<BulkActionResult>("/api/records/used", {
    record_ids: ids,
    is_used: isUsed,
  });
  return data;
}

export async function deleteRecord(id: string): Promise<BulkActionResult> {
  const { data } = await api.delete<BulkActionResult>(`/api/records/${id}`);
  return data;
}

export async function deleteRecords(ids: string[]): Promise<BulkActionResult> {
  const { data } = await api.post<BulkActionResult>("/api/records/bulk-delete", {
    record_ids: ids,
  });
  return data;
}

/** Outcome of an automatic correction attempt (see `POST /api/records/{id}/autofix`). */
export interface AutoFixResult {
  record_id: string;
  /** Issue codes the engine successfully addressed. */
  fixed: string[];
  /** Codes still auto-fixable - a retry may help. */
  remaining_fixable: string[];
  /** Codes needing a human decision; deliberately not attempted. */
  manual: string[];
  passes: number;
  initial_score: number;
  final_score: number;
  improved: boolean;
  /** Threshold verdicts, so the UI need not re-derive them from the score. */
  initial_passed: boolean;
  final_passed: boolean;
  /** True when the written file verifiably carries an sRGB profile. */
  srgb_embedded: boolean;
  history: Record<string, unknown>[];
  summary: string;
  /** The refreshed record, so callers need not refetch the list. */
  record: ImageRecord;
}

/**
 * Apply every automatically fixable correction to a record and re-score it.
 *
 * The backend writes the corrected file as the record's working copy, so the
 * preview must be refetched afterwards.
 */
export async function autoFixRecord(
  id: string,
  variant: "working" | "refined" | "upscaled" = "working"
): Promise<AutoFixResult> {
  const { data } = await api.post<AutoFixResult>(
    `/api/records/${id}/autofix`,
    null,
    { params: { variant } }
  );
  return data;
}

export async function fetchUploadTable(
  ids: string[]
): Promise<UploadTableResponse> {
  const { data } = await api.post<UploadTableResponse>("/api/upload-table", {
    record_ids: ids,
  });
  return data;
}

/** Trigger a browser download for a single staged asset. */
export function getDownloadUrl(recordId: string): string {
  return `${API_BASE_URL}/api/records/${recordId}/download`;
}

/** Trigger a browser download of a ZIP containing the given staged assets. */
export async function downloadRecordsZip(ids: string[]): Promise<void> {
  const response = await api.post(
    "/api/records/download-zip",
    { record_ids: ids },
    { responseType: "blob" }
  );
  const blobUrl = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = "adobe-stock-upload-batch.zip";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
}

export async function approveRecord(
  id: string,
  overrides?: ApproveOverrides
): Promise<ApproveResponse> {
  const { data } = await api.post<ApproveResponse>(
    `/api/records/${id}/approve`,
    overrides ?? {}
  );
  return data;
}

export async function approveBatch(ids: string[]): Promise<ApproveResponse[]> {
  const results = await Promise.allSettled(ids.map((id) => approveRecord(id)));
  return results
    .filter(
      (r): r is PromiseFulfilledResult<ApproveResponse> =>
        r.status === "fulfilled"
    )
    .map((r) => r.value);
}

export function getThumbnailUrl(record: ImageRecord): string | null {
  if (!record.thumbnail_path) return null;
  const filename = record.thumbnail_path.split(/[\\/]/).pop();
  if (!filename) return null;
  return `${API_BASE_URL}/thumbnails/${filename}`;
}

/**
 * URL for the image the pipeline is currently working on.
 *
 * `variant` selects the untouched original, the refined copy, the Stage 3
 * upscaled output, or (default) the current working file, which is what the
 * stage workspace previews.
 */
export function getPreviewUrl(
  recordId: string,
  variant: "working" | "original" | "refined" | "upscaled" = "working",
  /** Cache-buster; pass a changing value after a stage run to force a refetch. */
  version?: number | string
): string {
  const base = `${API_BASE_URL}/api/records/${recordId}/preview?variant=${variant}`;
  return version === undefined ? base : `${base}&v=${version}`;
}

// --------------------------------------------------------------------------- //
// Stage pipeline
// --------------------------------------------------------------------------- //

export async function fetchStages(): Promise<StageDefinition[]> {
  const { data } = await api.get<StageDefinition[]>("/api/stages");
  return data;
}

export async function fetchStageSummary(): Promise<StageSummary> {
  const { data } = await api.get<StageSummary>("/api/stages/summary");
  return data;
}

export async function fetchCategories(): Promise<AdobeCategory[]> {
  const { data } = await api.get<AdobeCategory[]>("/api/categories");
  return data;
}

export interface RunStageOptions {
  /** Stage 6 only: seconds to wait between LLM calls. */
  delaySeconds?: number;
  /** Stage 4/5 only: include the LLM semantic audit in scoring. */
  useSemantic?: boolean;
  /** Stage 3 only: the full upscale configuration. */
  upscale?: Partial<UpscaleOptions>;
}

/**
 * Start a batch stage operation.
 *
 * Returns immediately with a job handle; poll {@link fetchJob} for progress.
 * The batch runs server-side, so a large selection does not hold the request open.
 */
export async function runStage(
  stageKey: StageKey,
  recordIds: string[],
  options: RunStageOptions = {}
): Promise<StageJob> {
  const { data } = await api.post<StageJob>(`/api/stages/${stageKey}/run`, {
    record_ids: recordIds,
    delay_seconds: options.delaySeconds,
    use_semantic: options.useSemantic ?? true,
    upscale: options.upscale,
  });
  return data;
}

export async function fetchJob(jobId: string): Promise<StageJob> {
  const { data } = await api.get<StageJob>(`/api/jobs/${jobId}`);
  return data;
}

export async function fetchRecentJobs(limit = 10): Promise<StageJob[]> {
  const { data } = await api.get<StageJob[]>("/api/jobs", { params: { limit } });
  return data;
}

export async function cancelJob(jobId: string): Promise<StageJob> {
  const { data } = await api.post<StageJob>(`/api/jobs/${jobId}/cancel`);
  return data;
}

export interface MetadataUpdate {
  title?: string;
  description?: string;
  keywords?: string[];
  category?: number;
}

/** Apply a manual metadata edit. Only the supplied fields change. */
export async function updateMetadata(
  recordId: string,
  update: MetadataUpdate
): Promise<ImageRecord> {
  const { data } = await api.patch<ImageRecord>(
    `/api/records/${recordId}/metadata`,
    update
  );
  return data;
}

/** Return a record to Stage 1 so it can be reprocessed. */
export async function resetStage(recordId: string): Promise<ImageRecord> {
  const { data } = await api.post<ImageRecord>(
    `/api/records/${recordId}/reset-stage`
  );
  return data;
}

/** Preview the Adobe Stock CSV without downloading it. */
export async function previewCsv(recordIds?: string[]): Promise<CsvPreview> {
  const { data } = await api.post<CsvPreview>("/api/metadata/csv/preview", {
    record_ids: recordIds ?? null,
  });
  return data;
}

/** Download the Adobe Stock CSV for the given records (or all exportable rows). */
export async function downloadCsv(recordIds?: string[]): Promise<void> {
  const response = await api.post(
    "/api/metadata/csv",
    { record_ids: recordIds ?? null },
    { responseType: "blob" }
  );

  const blobUrl = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = "adobe-stock-metadata.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
}

export function formatFileSize(bytes: number): string {
  if (!bytes) return "0 MB";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default api;
