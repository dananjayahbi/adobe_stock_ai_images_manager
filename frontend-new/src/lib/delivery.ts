/**
 * Adobe Stock delivery downloads for a gallery selection: the template CSV on
 * its own, or the ZIP+CSV bundle.
 *
 * Adobe matches a CSV row to an uploaded image **by filename**, so the CSV and
 * the ZIP must come from one place: `/api/assets/bundle` builds the archive and
 * the CSV from the same staged records (`apply_names=True` in
 * `backend/routers/delivery.py`), which is what keeps the CSV `Filename`
 * column identical to the ZIP entry names. This module is only the client
 * half — fetching the blob and handing it to the browser.
 *
 * Errors arrive as FastAPI's `{"detail": "..."}` JSON; both helpers parse that
 * into a readable `Error` so the caller (dialog or page banner) can show the
 * real reason instead of a status code.
 */
import { API_BASE_URL } from "./client";

/** Mirrors `MAX_ZIP_FILES` in `backend/routers/delivery.py`. */
export const MAX_BUNDLE_FILES = 50;

/**
 * Download the Adobe Stock CSV for an explicit selection.
 *
 * `only_ready` is sent as `false` on purpose: the operator picked these exact
 * records, so the export honours the selection as-is (a published asset is not
 * METADATA_READY and would otherwise vanish from its own export). The CSV cap
 * (500 rows, `MAX_DELIVERY_BATCH`) is unreachable from the gallery because
 * `useRecords` loads at most 500 records.
 */
export async function downloadSelectionCsv(recordIds: string[]): Promise<void> {
  const response = await postDelivery("/api/assets/csv", recordIds);
  const filename =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ??
    "adobe-stock-metadata.csv";
  triggerBlob(await response.blob(), filename);
}

/**
 * Download the ZIP containing the selected images **and** their Adobe Stock
 * CSV (`adobe-stock-delivery.zip`).
 *
 * Same `only_ready: false` rationale as the CSV — but note the backend only
 * archives records that actually have a staged file, so the bundle stays a
 * faithful pairing of archive entries and CSV rows regardless. Selections over
 * `MAX_BUNDLE_FILES` are rejected by the server (400); the dialog disables the
 * option up front instead of letting the request fail.
 */
export async function downloadSelectionBundle(recordIds: string[]): Promise<void> {
  const response = await postDelivery("/api/assets/bundle", recordIds);
  const filename =
    filenameFromDisposition(response.headers.get("Content-Disposition")) ??
    "adobe-stock-delivery.zip";
  triggerBlob(await response.blob(), filename);
}

/** POST a delivery request; throws the backend's `detail` on failure. */
async function postDelivery(path: string, recordIds: string[]): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ record_ids: recordIds, only_ready: false }),
    // Cross-origin to the API host — without this the session cookie never
    // rides along and every delivery would answer 401.
    credentials: "include",
  });
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}.`;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof (body as { detail: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // Non-JSON error body (proxy/HTML); keep the status fallback.
    }
    throw new Error(detail);
  }
  return response;
}

/** `attachment; filename="x.zip"` → `x.zip`; null when the header is absent. */
function filenameFromDisposition(value: string | null): string | null {
  if (!value) return null;
  const match = /filename="?([^";]+)"?/i.exec(value);
  return match ? match[1] : null;
}

function triggerBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url); // the browser has started the download by now
}
