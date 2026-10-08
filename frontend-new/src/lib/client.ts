/**
 * The shared HTTP client for the batch studio.
 *
 * One axios instance so the base URL and error normalisation cannot drift
 * between features. The backend's `detail` string is surfaced verbatim —
 * axios's generic "Request failed with status code 400" hides the reason.
 */
import axios from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8001";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120_000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail =
      error?.response?.data?.detail ?? error?.message ?? "Unexpected network error.";
    return Promise.reject(new Error(String(detail)));
  }
);

/** Thumbnail URL for a record (thumbnails are mounted at /thumbnails). */
export function thumbnailUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  const filename = path.split(/[\\/]/).pop();
  return filename ? `${API_BASE_URL}/thumbnails/${filename}` : null;
}

export default api;
