/** Typed API client for step profiles. */
import { api } from "./client";
import type { MediaType, StepProfile, BatchStep } from "./types";

export async function listProfiles(mediaType?: MediaType): Promise<StepProfile[]> {
  const { data } = await api.get("/api/step-profiles", {
    params: mediaType ? { media_type: mediaType } : {},
  });
  return data.items;
}

export async function createProfile(payload: {
  name: string;
  media_type: MediaType;
  steps: BatchStep[];
}): Promise<StepProfile> {
  const { data } = await api.post("/api/step-profiles", payload);
  return data;
}

export async function deleteProfile(id: string): Promise<{ deleted: string }> {
  const { data } = await api.delete(`/api/step-profiles/${id}`);
  return data;
}
