/**
 * Cross-tab hand-off for the generated upload table.
 *
 * The gallery writes the selected record ids to localStorage under a short
 * token, then opens `/upload-table?token=...` in a new tab. localStorage is
 * shared across same-origin tabs, which sessionStorage is not.
 */

const KEY_PREFIX = "adobe-stock:upload-table:";
const MAX_ENTRIES = 8;

export interface UploadTableHandoff {
  ids: string[];
  createdAt: number;
}

function makeToken(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function pruneOldEntries(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key?.startsWith(KEY_PREFIX)) keys.push(key);
    }
    if (keys.length <= MAX_ENTRIES) return;

    const stamped = keys
      .map((key) => {
        try {
          const parsed = JSON.parse(localStorage.getItem(key) ?? "{}");
          return { key, createdAt: Number(parsed?.createdAt ?? 0) };
        } catch {
          return { key, createdAt: 0 };
        }
      })
      .sort((a, b) => a.createdAt - b.createdAt);

    for (const entry of stamped.slice(0, stamped.length - MAX_ENTRIES)) {
      localStorage.removeItem(entry.key);
    }
  } catch {
    // Storage may be unavailable (private mode); ignore.
  }
}

/** Persist a selection and return its token. */
export function saveUploadTableSelection(ids: string[]): string {
  const token = makeToken();
  try {
    const payload: UploadTableHandoff = { ids, createdAt: Date.now() };
    localStorage.setItem(`${KEY_PREFIX}${token}`, JSON.stringify(payload));
    pruneOldEntries();
  } catch {
    // Ignore - the caller falls back to query-string ids.
  }
  return token;
}

/** Read a previously persisted selection, or null when absent/corrupt. */
export function readUploadTableSelection(token: string): string[] | null {
  try {
    const raw = localStorage.getItem(`${KEY_PREFIX}${token}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as UploadTableHandoff;
    return Array.isArray(parsed?.ids) ? parsed.ids.map(String) : null;
  } catch {
    return null;
  }
}

/** Remove a consumed hand-off entry. */
export function clearUploadTableSelection(token: string): void {
  try {
    localStorage.removeItem(`${KEY_PREFIX}${token}`);
  } catch {
    // Ignore.
  }
}
