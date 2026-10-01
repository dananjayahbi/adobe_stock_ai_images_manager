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

/** Draft values the dialog edits before saving. */
export interface SettingsDraft {
  llm_base_url: string;
  llm_model: string;
  llm_api_key: string;
  llm_context_window: string;
  brave_search_enabled: boolean;
  brave_search_api_key: string;
  brave_search_rate_limit: string;
  research_max_tool_calls: string;
}

const EMPTY_DRAFT: SettingsDraft = {
  llm_base_url: "",
  llm_model: "",
  llm_api_key: "",
  llm_context_window: "",
  brave_search_enabled: false,
  brave_search_api_key: "",
  brave_search_rate_limit: "1",
  research_max_tool_calls: "",
};

export interface UseAppSettingsResult {
  settings: AppSettings | null;
  draft: SettingsDraft;
  isLoading: boolean;
  isSaving: boolean;
  isTesting: boolean;
  /** Load or save failure. */
  error: string | null;
  /** Result of the most recent connection test, cleared when fields change. */
  testResult: SettingsTestResult | null;
  setField: <K extends keyof SettingsDraft>(key: K, value: SettingsDraft[K]) => void;
  save: () => Promise<void>;
  /** `probeSearch` also exercises the web-search provider. */
  test: (options?: { probeSearch?: boolean }) => Promise<void>;
  reset: () => Promise<void>;
  reload: () => Promise<void>;
}

/**
 * State for the Settings modal.
 *
 * The draft is seeded from the stored values, falling back to the effective
 * ones so the fields are never blank for an operator who has only ever used
 * `.env` - an empty form would read as "nothing configured".
 *
 * The API key field is seeded blank on purpose. The server only returns a mask,
 * and submitting a blank key means "keep the stored one", so a save that never
 * touches the field cannot disturb a working credential.
 *
 * @param isOpen When false the hook fetches nothing. The modal is mounted on
 *   every route (inside the nav bar), so loading eagerly would issue a request
 *   on every page view for a dialog the operator may never open. Re-opening
 *   refetches, which is desirable: settings can also be edited from `.env` or
 *   another tab.
 */
export function useAppSettings(isOpen = true): UseAppSettingsResult {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<SettingsDraft>(EMPTY_DRAFT);
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setSaving] = useState(false);
  const [isTesting, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      brave_search_enabled: next.brave_search_enabled,
      // Seeded blank for the same reason the LLM key is: the server only returns
      // a mask, and a blank field means "keep the stored key".
      brave_search_api_key: "",
      brave_search_rate_limit: String(next.brave_search_rate_limit ?? 1),
      research_max_tool_calls: String(next.research_max_tool_calls ?? 24),
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
    if (!isOpen) return;
    void reload();
  }, [isOpen, reload]);

  const setField = useCallback<UseAppSettingsResult["setField"]>((key, value) => {
    setDraft((current) => ({ ...current, [key]: value }));
    // A stale verdict would misrepresent the edited values.
    setTestResult(null);
  }, []);

  const buildPayload = useCallback((): SettingsUpdate => {
    const window = Number.parseInt(draft.llm_context_window, 10);
    const payload: SettingsUpdate = {
      llm_base_url: draft.llm_base_url.trim(),
      llm_model: draft.llm_model.trim(),
      brave_search_enabled: draft.brave_search_enabled,
    };
    if (Number.isFinite(window)) {
      payload.llm_context_window = window;
    }
    // Only send the key when the operator actually typed one; a blank value is
    // already the server's "leave it alone" signal, but omitting it entirely
    // makes the intent explicit.
    const key = draft.llm_api_key.trim();
    if (key) payload.llm_api_key = key;

    const braveKey = draft.brave_search_api_key.trim();
    if (braveKey) payload.brave_search_api_key = braveKey;

    const rate = Number.parseFloat(draft.brave_search_rate_limit);
    if (Number.isFinite(rate)) payload.brave_search_rate_limit = rate;

    const calls = Number.parseInt(draft.research_max_tool_calls, 10);
    if (Number.isFinite(calls)) payload.research_max_tool_calls = calls;

    return payload;
  }, [draft]);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      apply(await updateSettings(buildPayload()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save settings.");
      throw err;
    } finally {
      setSaving(false);
    }
  }, [apply, buildPayload]);

  const test = useCallback(async (options: { probeSearch?: boolean } = {}) => {
    setTesting(true);
    setError(null);
    try {
      const result = await testSettings(buildPayload(), options);
      setTestResult(result);
    } catch (err) {
      setTestResult({
        ok: false,
        error: err instanceof Error ? err.message : "Connection test failed.",
      });
    } finally {
      setTesting(false);
    }
  }, [buildPayload]);

  const reset = useCallback(async () => {
    setSaving(true);
    setError(null);
    setTestResult(null);
    try {
      apply(await resetSettings());
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
    testResult,
    setField,
    save,
    test,
    reset,
    reload,
  };
}

export default useAppSettings;
