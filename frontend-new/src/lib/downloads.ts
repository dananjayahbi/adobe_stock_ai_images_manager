/**
 * Gallery download helpers.
 *
 * Single images go straight through an anchor (`?download=1` sets the
 * attachment header server-side). Multi-selection offers the operator the
 * choice in `DownloadDialog`: fire the files one at a time, or ask the backend
 * for one ZIP.
 */
import { API_BASE_URL, api } from "./client";

/** Direct (single) download of a record's current image. */
export function downloadRecordFile(recordId: string): void {
  triggerAnchor(`${API_BASE_URL}/api/records/${recordId}/file?download=1`);
}

/**
 * Download many files one after another via `GET .../file?download=1`.

 * The pauses keep the browser from coalescing the navigations; most browsers
 * also ask the operator for permission the first time ("Allow multiple
 * downloads"), which is the expected UX for this option.
 */
export async function downloadSequentially(recordIds: string[]): Promise<void> {
  for (const id of recordIds) {
    downloadRecordFile(id);
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
}

/** Download many files as a single ZIP built by the backend. */
export async function downloadZip(recordIds: string[]): Promise<void> {
  const { data } = await api.post(
    "/api/records/file-zip",
    { record_ids: recordIds },
    { responseType: "blob" }
  );
  const url = URL.createObjectURL(data);
  triggerAnchor(url, "gallery-images.zip");
  URL.revokeObjectURL(url); // the browser has started the download by now
}

function triggerAnchor(href: string, download?: string): void {
  const anchor = document.createElement("a");
  anchor.href = href;
  if (download) anchor.download = download;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
