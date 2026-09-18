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
  limit?: number;
  offset?: number;
}): Promise<RecordListResponse> {
  const { data } = await api.get<RecordListResponse>("/api/records", { params });
  return data;
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
