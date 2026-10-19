/**
 * Shared encoding for gallery drag-and-drop (selected images → folder cards).
 *
 * Browsers mask `DataTransfer.getData` during `dragover` (only the *types* are
 * visible before drop), so the dragged ids are mirrored in a same-document
 * variable that drop targets read for hover hints; the real payload is still
 * what `drop` decodes.
 */

/** MIME type identifying a drag that carries gallery record ids. */
export const RECORD_IDS_MIME = "application/x-adobe-record-ids";

/** Ids of the drag currently running in this document (hover-hint mirror). */
let activeDragIds: string[] = [];

/** True when a drag event carries our record-id payload. */
export function hasRecordIds(dataTransfer: DataTransfer | null): boolean {
  return !!dataTransfer && Array.from(dataTransfer.types).includes(RECORD_IDS_MIME);
}

/** Start a drag: mirror the ids for hover hints and attach the payload. */
export function beginDrag(dataTransfer: DataTransfer, ids: string[]): void {
  activeDragIds = ids;
  dataTransfer.effectAllowed = "move";
  dataTransfer.setData(RECORD_IDS_MIME, JSON.stringify(ids));
  // Readable by anything (older browsers, external drop targets).
  dataTransfer.setData(
    "text/plain",
    ids.length === 1 ? "1 image" : `${ids.length} images`
  );
}

/** Ids mirrored for the currently-running drag (hover hints). */
export function activeIds(): string[] {
  return activeDragIds;
}

/** Decode the ids from a drop event; [] when the payload is not ours. */
export function getRecordIds(dataTransfer: DataTransfer | null): string[] {
  if (!dataTransfer) return [];
  try {
    const parsed: unknown = JSON.parse(dataTransfer.getData(RECORD_IDS_MIME) || "[]");
    return Array.isArray(parsed)
      ? parsed.filter((value): value is string => typeof value === "string")
      : [];
  } catch {
    return [];
  }
}

/** Clear the mirror (drop handled, or the drag ended elsewhere). */
export function endDrag(): void {
  activeDragIds = [];
}
