/**
 * Asset delivery client — naming, forced acceptance, and CSV/ZIP export.
 *
 * From Stage 6 onward the operator stops *processing* images and starts
 * *delivering* them, and these three concerns follow the record wherever it
 * sits (metadata-ready or published). Keeping them in one module means the
 * Metadata page and the Gallery share one contract instead of each growing its
 * own copy of the CSV/ZIP logic.
 *
 * The central fact behind all of it: Adobe matches a CSV row to an uploaded
 * image **by filename**, so the name shown in the CSV must be the name of the
 * file that gets uploaded.
 */

import { api } from "./client";

export interface RenameResultItem {
  record_id: string;
  filename: string;
  /** The new name, or null when the override was cleared. */
  download_name: string | null;
  changed: boolean;
  error?: string | null;
}

export interface RenameResponse {
  items: RenameResultItem[];
  updated: number;
  failed: number;
}

export interface ForcedAcceptResultItem {
  record_id: string;
  accepted: boolean;
  previous_stage: string;
  new_stage: string | null;
  score: number | null;
  reason: string;
}

export interface ForcedAcceptResponse {
  items: ForcedAcceptResultItem[];
  accepted: number;
  refused: number;
}

export interface DeliverySelection {
  recordIds: string[];
  /**
   * Whether to restrict the export to records whose metadata is ready.
   *
   * Defaults to true on the server. The Gallery passes false for published
   * assets, and the Metadata page passes false when exporting a selection that
   * was force-accepted before the gate cleared it.
   */
  onlyReady?: boolean;
}

/** Set (or clear, with a blank name) the upload filename for records. */
export async function renameAssets(
  items: { recordId: string; name: string }[]
): Promise<RenameResponse> {
  const { data } = await api.post<RenameResponse>("/api/assets/rename", {
    items: items.map((item) => ({ record_id: item.recordId, name: item.name })),
  });
  return data;
}

/**
 * Ask what each name would become if rebuilt from the generated title.
 *
 * Non-mutating: this is the review step behind "rename them all", so the
 * operator can see the whole batch before committing to it.
 */
export async function suggestNames(recordIds: string[]): Promise<RenameResponse> {
  const { data } = await api.post<RenameResponse>("/api/assets/rename-suggest", {
    items: recordIds.map((recordId) => ({ record_id: recordId, name: "" })),
  });
  return data;
}

/**
 * Adopt the metadata model's proposed filenames for these records.
 *
 * Distinct from `suggestNames`, which derives a name from the *title*. This one
 * applies the name the model chose while looking at the image, which is usually
 * the better name — but it writes immediately, because applying a stored
 * proposal is a deliberate one-click decision rather than a draft.
 */
export async function applySuggestedNames(
  recordIds: string[]
): Promise<RenameResponse> {
  const { data } = await api.post<RenameResponse>(
    "/api/assets/apply-suggested-names",
    { items: recordIds.map((recordId) => ({ record_id: recordId, name: "" })) }
  );
  return data;
}

/** Force records past the acceptance gate, recording the reason. */
export async function forceAccept(
  recordIds: string[],
  reason = ""
): Promise<ForcedAcceptResponse> {
  const { data } = await api.post<ForcedAcceptResponse>("/api/assets/force-accept", {
    record_ids: recordIds,
    reason,
  });
  return data;
}

/** Preview the CSV for a selection without downloading it. */
export async function previewSelectionCsv(
  selection: DeliverySelection
): Promise<{ csv_text: string; row_count: number; skipped: string[]; warnings: string[] }> {
  const { data } = await api.post("/api/assets/csv/preview", {
    record_ids: selection.recordIds,
    only_ready: selection.onlyReady ?? true,
  });
  return data;
}

/** Download the Adobe Stock CSV for a selection. */
export async function downloadSelectionCsv(
  selection: DeliverySelection
): Promise<void> {
  const response = await api.post(
    "/api/assets/csv",
    { record_ids: selection.recordIds, only_ready: selection.onlyReady ?? true },
    { responseType: "blob" }
  );
  triggerBlobDownload(response.data as Blob, "adobe-stock-metadata.csv");
}

/**
 * Download a ZIP containing the selected images **and** their CSV.
 *
 * Bundled deliberately: fetching the images and the CSV from separate actions is
 * how the filenames drift apart, and a CSV naming a file that is not in the
 * archive is worthless to Adobe.
 */
export async function downloadSelectionBundle(
  selection: DeliverySelection
): Promise<void> {
  const response = await api.post(
    "/api/assets/bundle",
    { record_ids: selection.recordIds, only_ready: selection.onlyReady ?? true },
    { responseType: "blob" }
  );
  triggerBlobDownload(response.data as Blob, "adobe-stock-delivery.zip");
}

/** Shared blob-download plumbing, so the two download paths cannot diverge. */
function triggerBlobDownload(blob: Blob, filename: string): void {
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = blobUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
}
