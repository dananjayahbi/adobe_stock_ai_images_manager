/**
 * Byte/size formatting shared by the setup cards and the install modal.
 *
 * One source of truth so the modal's "61.0 / 147.0 MB" counter, a card's
 * "124 MB" size and the storage card's "1.4 GB" total can never drift apart.
 */

const MB = 1024 * 1024;
const GB = 1024 * MB;

/** Bytes → "61.0 MB" (one decimal — the download modal's byte counter). */
export function formatMb(bytes: number): string {
  return `${(Math.max(0, bytes) / MB).toFixed(1)} MB`;
}

/** Bytes → "61.0 / 147.0 MB" — one shared unit, as the modal counter shows. */
export function formatMbRange(done: number, total: number): string {
  const safeDone = Math.max(0, done);
  const safeTotal = Math.max(0, total);
  return `${(safeDone / MB).toFixed(1)} / ${(safeTotal / MB).toFixed(1)} MB`;
}

/** A `size_mb` field → "124 MB" or "124.5 MB". */
export function formatSizeMb(sizeMb: number): string {
  return `${Number.isInteger(sizeMb) ? sizeMb : sizeMb.toFixed(1)} MB`;
}

/** Bytes → adaptive "1.4 GB" (≥ 1 GB) or "611 MB". */
export function formatBytes(bytes: number): string {
  const safe = Math.max(0, bytes);
  if (safe >= GB) return `${(safe / GB).toFixed(1)} GB`;
  return `${Math.round(safe / MB)} MB`;
}
