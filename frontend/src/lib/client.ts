/**
 * The shared HTTP client.
 *
 * Extracted from `api.ts` so feature-specific modules (settings, upload, …) can
 * import the configured instance without depending on the entire stage API
 * surface. Keeping one instance means the base URL and the error normalisation
 * below cannot drift between features.
 */

import axios from "axios";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8100";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Surface the backend's `detail` string rather than axios's generic
    // "Request failed with status code 400", which hides the actual reason.
    const detail =
      error?.response?.data?.detail ??
      error?.message ??
      "Unexpected network error.";
    return Promise.reject(new Error(String(detail)));
  }
);

export default api;
