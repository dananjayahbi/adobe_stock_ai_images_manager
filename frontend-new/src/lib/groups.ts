/** Typed API client for gallery folders (groups). */
import { api } from "./client";
import type { GalleryGroup } from "./types";

export interface GroupList {
  items: GalleryGroup[];
}

export async function fetchGroups(): Promise<GalleryGroup[]> {
  const { data } = await api.get<GroupList>("/api/groups");
  return data.items;
}

export async function createGroup(
  name: string,
  recordIds: string[] = []
): Promise<GalleryGroup> {
  const { data } = await api.post<GalleryGroup>("/api/groups", {
    name,
    record_ids: recordIds,
  });
  return data;
}

export async function renameGroup(id: string, name: string): Promise<GalleryGroup> {
  const { data } = await api.patch<GalleryGroup>(`/api/groups/${id}`, { name });
  return data;
}

/** Delete the folder only — its images fall back to the top level. */
export async function deleteGroup(id: string): Promise<GalleryGroup> {
  const { data } = await api.delete<GalleryGroup>(`/api/groups/${id}`);
  return data;
}

/** Move records into a folder, or out of any folder with `groupId = null`. */
export async function assignRecords(
  recordIds: string[],
  groupId: string | null
): Promise<void> {
  await api.put("/api/groups/assign", {
    record_ids: recordIds,
    group_id: groupId,
  });
}
