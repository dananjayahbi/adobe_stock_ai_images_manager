/**
 * Filesystem probes for the Config page — kept out of settings.ts so the
 * settings client stays a pure /api/settings client.
 */
import { api } from "./client";

/** GET /api/fs/root — where the mobile app's image picker will browse. */
export interface FsRoot {
  /** A source folder has been saved (path may still be stale on disk). */
  configured: boolean;
  /** The saved absolute path; null when unconfigured. */
  path: string | null;
  /** The configured path currently exists on the server machine. */
  exists: boolean;
}

export async function fetchFsRoot(): Promise<FsRoot> {
  const { data } = await api.get<FsRoot>("/api/fs/root");
  return data;
}
