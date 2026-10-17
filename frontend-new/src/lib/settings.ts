/**
 * Runtime application settings client (the /settings page's data layer).
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
  min_brave_rate: number;
  max_brave_rate: number;
  min_keyword_target: number;
  max_keyword_target: number;
  min_metadata_delay: number;
  max_metadata_delay: number;
  max_extra_instructions: number;
  max_priority_terms_chars: number;
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
  /** Metadata generation: keyword count, pacing, and appended instructions. */
  metadata_keyword_target: number;
  metadata_delay_seconds: number;
  metadata_extra_instructions: string;
  /** High-intent commercial terms pulled to the first 10 keyword positions. */
  metadata_priority_terms: string;
  /** Root folder the mobile app's image picker browses. "" = unset. */
  source_folder: string;
  /** Web-search provider for the research agent (Brave → DuckDuckGo fallback). */
  brave_search_enabled: boolean;
  /** Display-only Brave key mask. Never a usable key. */
  brave_search_api_key_masked: string;
  brave_search_api_key_set: boolean;
  brave_search_rate_limit: number;
  /** What will actually run first — derived, so an enabled-but-keyless
   *  configuration can never be shown as active. */
  effective_uses_brave: boolean;
  effective_search_provider: "brave" | "duckduckgo";
  defaults: SettingsDefaults;
  bounds: SettingsBounds;
}

/**
 * Partial update. Omitted fields are left untouched.
 *
 * Sending `llm_api_key: ""` keeps the stored key, which is what makes a
 * "save without retyping the key" flow safe. Use `clear_api_key` to remove it.
 * `brave_search_api_key` follows the same blank-means-unchanged contract.
 */
export interface SettingsUpdate {
  llm_base_url?: string;
  llm_model?: string;
  llm_api_key?: string;
  llm_context_window?: number;
  clear_api_key?: boolean;
  brave_search_enabled?: boolean;
  brave_search_api_key?: string;
  brave_search_rate_limit?: number;
  clear_brave_search_key?: boolean;
  metadata_keyword_target?: number;
  metadata_delay_seconds?: number;
  metadata_extra_instructions?: string;
  metadata_priority_terms?: string;
  /** Root folder for the mobile picker; "" explicitly unsets it. */
  source_folder?: string;
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
