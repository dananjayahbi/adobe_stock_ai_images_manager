"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type AppSettings,
  fetchSettings,
  resetSettings,
  type SettingsTestResult,
  type SettingsUpdate,
  testSettings,
  updateSettings,
} from "@/lib/settings";

/** Draft values the settings cards edit before saving. */
export interface SettingsDraft {
  llm_base_url: string;
  llm_model: string;
  llm_api_key: string;
  llm_context_window: string;
  brave_search_enabled: boolean;
  brave_search_api_key: string;
  brave_search_rate_limit: string;
  metadata_keyword_target: string;
  metadata_delay_seconds: string;
  metadata_extra_instructions: string;
  metadata_priority_terms: string;
}

const EMPTY_DRAFT: SettingsDraft = {
  llm_base_url: "",
  llm_model: "",
  llm_api_key: "",
  llm_context_window: "",
  brave_search_enabled: false,
  brave_search_api_key: "",
  brave_search_rate_limit: "1",
  metadata_keyword_target: "49",
  metadata_delay_seconds: "2",
  metadata_extra_instructions: "",
  metadata_priority_terms: "",
};

export interface UseSettingsResult {
  settings: AppSettings | null;
  draft: SettingsDraft;
  isLoading: boolean;
  isSaving: boolean;
  isTesting: boolean;
  /** Load or save failure. */
  error: string | null;
  notice: string | null;
  /** Result of the most recent connection test, cleared when fields change. */
  testResult: SettingsTestResult | null;
  setField: <K extends keyof SettingsDraft>(key: K, value: SettingsDraft[K]) => void;
  save: () => Promise<void>;
  test: () => Promise<void>;
  reset: () => Promise<void>;
}

/**
 * State for the /settings page cards.
 *
 * The draft is seeded from the stored values, falling back to the effective
 * ones so the fields are never blank for an operator who has only ever used
 * `.env` - an empty form would read as "nothing configured".
 *
 * The API key field is seeded blank on purpose. The server only returns a mask,
 * and submitting a blank key means "keep the stored one", so a save that never
 * touches the field cannot disturb a working credential.
 */
export function useSettings(): UseSettingsResult {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<SettingsDraft>(EMPTY_DRAFT);
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setSaving] = useState(false);
  const [isTesting, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<SettingsTestResult | null>(null);

  const apply = useCallback((next: AppSettings) => {
    setSettings(next);
    setDraft({
      llm_base_url: next.llm_base_url || next.effective_base_url,
      llm_model: next.llm_model || next.effective_model,
      llm_api_key: "",
      llm_context_window: String(
        next.llm_context_window || next.effective_context_window
      ),
      metadata_keyword_target: String(next.metadata_keyword_target ?? 49),
      metadata_delay_seconds: String(next.metadata_delay_seconds ?? 2),
      metadata_extra_instructions: next.metadata_extra_instructions ?? "",
      metadata_priority_terms: next.metadata_priority_terms ?? "",
      brave_search_enabled: next.brave_search_enabled,
      // Blank-seeded like the LLM key: the server only returns a mask.
      brave_search_api_key: "",
      brave_search_rate_limit: String(next.brave_search_rate_limit ?? 1),
    });
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      apply(await fetchSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const setField = useCallback<UseSettingsResult["setField"]>((key, value) => {
    setDraft((current) => ({ ...current, [key]: value }));
    // A stale verdict would misrepresent the edited values.
    setTestResult(null);
    setNotice(null);
  }, []);

  const buildPayload = (): SettingsUpdate => {
    const window = Number.parseInt(draft.llm_context_window, 10);
    const payload: SettingsUpdate = {
      llm_base_url: draft.llm_base_url.trim(),
      llm_model: draft.llm_model.trim(),
    };
    if (Number.isFinite(window)) payload.llm_context_window = window;

    // Only send the key when the operator actually typed one; a blank value is
    // already the server's "leave it alone" signal, but omitting it entirely
    // makes the intent explicit.
    const key = draft.llm_api_key.trim();
    if (key) payload.llm_api_key = key;

    // Brave: the toggle always travels (it is the point of the card), the key
    // only when typed, and the rate only when it parses — same contracts as the
    // LLM half.
    payload.brave_search_enabled = draft.brave_search_enabled;
    const braveKey = draft.brave_search_api_key.trim();
    if (braveKey) payload.brave_search_api_key = braveKey;
    const rate = Number.parseFloat(draft.brave_search_rate_limit);
    if (Number.isFinite(rate)) payload.brave_search_rate_limit = rate;

    const target = Number.parseInt(draft.metadata_keyword_target, 10);
    if (Number.isFinite(target)) payload.metadata_keyword_target = target;

    const delay = Number.parseFloat(draft.metadata_delay_seconds);
    if (Number.isFinite(delay)) payload.metadata_delay_seconds = delay;

    payload.metadata_extra_instructions = draft.metadata_extra_instructions;
    payload.metadata_priority_terms = draft.metadata_priority_terms;
    return payload;
  };

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      apply(await updateSettings(buildPayload()));
      setNotice("Settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
    } finally {
      setSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apply, draft]);

  const test = useCallback(async () => {
    setTesting(true);
    setError(null);
    try {
      setTestResult(await testSettings(buildPayload()));
    } catch (err) {
      setTestResult({
        ok: false,
        error: err instanceof Error ? err.message : "Connection test failed.",
      });
    } finally {
      setTesting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const reset = useCallback(async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    setTestResult(null);
    try {
      apply(await resetSettings());
      setNotice("Cleared saved overrides — .env values now apply.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reset settings.");
    } finally {
      setSaving(false);
    }
  }, [apply]);

  return {
    settings,
    draft,
    isLoading,
    isSaving,
    isTesting,
    error,
    notice,
    testResult,
    setField,
    save,
    test,
    reset,
  };
}

export default useSettings;
