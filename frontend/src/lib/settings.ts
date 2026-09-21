/**
 * Runtime application settings (the Settings modal's data layer).
 *
 * Mirrors `backend/schemas.py` settings schemas. The API never returns the raw
 * API key - only a mask and an `llm_api_key_set` flag - so this client cannot
 * leak a credential even by accident.
 */

import { api } from "./client";

export interface SettingsDefaults {
  llm_base_url: string;
  llm_model: string;
  llm_context_window: number;
}

export interface SettingsBounds {
  min_context_window: number;
  max_context_window: number;
}

export interface AppSettings {
  /** Values the operator stored. Empty when they have never saved. */
  llm_base_url: string;
  llm_model: string;
  llm_context_window: number;
  /** Display-only mask, e.g. `••••••••abcd`. Never a usable key. */
  llm_api_key_masked: string;
  llm_api_key_set: boolean;
  /** What a request would actually use right now (stored value or .env). */
  effective_base_url: string;
  effective_model: string;
  effective_context_window: number;
  /** Long edge images are downscaled to, derived from the context window. */
  effective_image_max_dim: number;
  defaults: SettingsDefaults;
  bounds: SettingsBounds;
}

/**
 * Partial update. Omitted fields are left untouched.
 *
 * Sending `llm_api_key: ""` keeps the stored key, which is what makes a
 * "save without retyping the key" flow safe. Use `clear_api_key` to remove it.
 */
export interface SettingsUpdate {
  llm_base_url?: string;
  llm_model?: string;
  llm_api_key?: string;
  llm_context_window?: number;
  clear_api_key?: boolean;
}

export interface SettingsTestResult {
  ok: boolean;
  model?: string | null;
  reply?: string | null;
  error?: string | null;
}

export async function fetchSettings(): Promise<AppSettings> {
  const { data } = await api.get<AppSettings>("/api/settings");
  return data;
}

export async function updateSettings(
  payload: SettingsUpdate
): Promise<AppSettings> {
  const { data } = await api.put<AppSettings>("/api/settings", payload);
  return data;
}

/**
 * Probe the endpoint with a short text request.
 *
 * Candidate values are validated but **not persisted**, so testing an endpoint
 * the operator is still experimenting with cannot pin it as the live config.
 * The probe returns a failure as data rather than throwing, because a bad
 * endpoint is a normal state the dialog renders inline.
 */
export async function testSettings(
  payload: SettingsUpdate = {}
): Promise<SettingsTestResult> {
  const { data } = await api.post<SettingsTestResult>("/api/settings/test", payload);
  return data;
}

export async function resetSettings(): Promise<AppSettings> {
  const { data } = await api.post<AppSettings>("/api/settings/reset");
  return data;
}
