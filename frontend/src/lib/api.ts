import axios from "axios";

// ...existing code...
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

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

export function formatFileSize(bytes: number): string {
  if (!bytes) return "0 MB";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default api;
