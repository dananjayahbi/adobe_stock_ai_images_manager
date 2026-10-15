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
  // The session cookie is set by localhost:8001; XHR from :3100 is a
  // different origin, so the browser only attaches it with credentials.
  withCredentials: true,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";

    // A 401 anywhere but the login call means the session died server-side
    // (rotated secret, expired): clear the stale HttpOnly cookie the browser
    // still holds, then land on /login — never from /login itself, or a bad
    // cookie would loop forever.
    if (status === 401 && !url.includes("/api/auth/login")) {
      if (typeof window !== "undefined") {
        void fetch(`${API_BASE_URL}/api/auth/logout`, {
          method: "POST",
          credentials: "include",
        }).catch(() => {
          /* cookie already gone or backend down — the redirect still stands */
        });
        if (window.location.pathname !== "/login") {
          window.location.assign("/login");
        }
      }
    }

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
