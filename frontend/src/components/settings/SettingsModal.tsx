"use client";

import { RotateCcw, Save, Settings2, Sparkles, Zap } from "lucide-react";
import { useMemo } from "react";

import { SettingsField, controlClass } from "@/components/settings/SettingsField";
import {
  SettingsNotice,
  VisionModelNote,
} from "@/components/settings/SettingsNotice";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useAppSettings } from "@/hooks/useAppSettings";

export interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/** Preset context windows covering the common vision models. */
const WINDOW_PRESETS: Array<{ label: string; value: number }> = [
  { label: "8K", value: 8192 },
  { label: "32K", value: 32768 },
  { label: "128K", value: 131072 },
  { label: "200K", value: 200000 },
  { label: "1M", value: 1000000 },
];

/**
 * System settings dialog.
 *
 * Configures the OpenAI-compatible endpoint every AI feature uses. The values
 * are stored server-side (see `backend/services/app_settings.py`), so they
 * apply to the running backend immediately - no restart and no `.env` edit.
 */
export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const controller = useAppSettings(isOpen);
  const {
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
  } = controller;

  const windowError = useMemo(() => {
    if (!settings) return null;
    const value = Number.parseInt(draft.llm_context_window, 10);
    if (!Number.isFinite(value)) return "Enter the context window in tokens.";
    const { min_context_window, max_context_window } = settings.bounds;
    if (value < min_context_window || value > max_context_window) {
      return `Must be between ${min_context_window.toLocaleString()} and ${max_context_window.toLocaleString()} tokens.`;
    }
    return null;
  }, [draft.llm_context_window, settings]);

  const isBusy = isSaving || isTesting;
  const canSave =
    !isBusy &&
    !!draft.llm_base_url.trim() &&
    !!draft.llm_model.trim() &&
    !windowError;

  async function handleSave() {
    try {
      await save();
      onClose();
    } catch {
      // `error` already carries the message; keep the dialog open so the
      // operator can correct the field rather than losing their input.
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      isBusy={isBusy}
      size="lg"
      icon={<Settings2 className="h-4 w-4" aria-hidden />}
      title="System settings"
      description="Point the studio at any OpenAI-compatible endpoint. Used for metadata generation and the semantic quality audit."
      footer={
        <>
          <Button
            variant="ghost"
            size="sm"
            icon={<RotateCcw className="h-3.5 w-3.5" aria-hidden />}
            disabled={isBusy || isLoading}
            onClick={() => void reset()}
            title="Clear saved overrides and fall back to the .env values"
          >
            Reset to defaults
          </Button>
          <div className="flex-1" />
          <Button variant="subtle" size="sm" disabled={isBusy} onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={<Zap className="h-3.5 w-3.5" aria-hidden />}
            disabled={!canSave}
            isLoading={isTesting}
            onClick={() => void test()}
          >
            Test connection
          </Button>
          <Button
            variant="primary"
            size="sm"
            icon={<Save className="h-3.5 w-3.5" aria-hidden />}
            disabled={!canSave}
            isLoading={isSaving}
            onClick={() => void handleSave()}
          >
            Save
          </Button>
        </>
      }
    >
      {isLoading ? (
        <p className="py-6 text-center text-xs text-navy-400">Loading settings…</p>
      ) : (
        <div className="space-y-4">
          <VisionModelNote />

          <SettingsField
            id="settings-base-url"
            label="Base URL"
            hint={
              settings?.effective_base_url &&
              settings.effective_base_url !== draft.llm_base_url
                ? `Currently in use: ${settings.effective_base_url}`
                : "The OpenAI-compatible root, including the version path, e.g. https://api.openai.com/v1"
            }
          >
            <input
              id="settings-base-url"
              type="url"
              inputMode="url"
              spellCheck={false}
              autoComplete="off"
              placeholder="https://api.openai.com/v1"
              className={controlClass(false)}
              value={draft.llm_base_url}
              disabled={isBusy}
              onChange={(event) => setField("llm_base_url", event.target.value)}
            />
          </SettingsField>

          <SettingsField
            id="settings-model"
            label="Model ID"
            hint="The exact model identifier the endpoint expects, e.g. gpt-4o-mini or a gateway pool name."
          >
            <input
              id="settings-model"
              type="text"
              spellCheck={false}
              autoComplete="off"
              placeholder="gpt-4o-mini"
              className={controlClass(false)}
              value={draft.llm_model}
              disabled={isBusy}
              onChange={(event) => setField("llm_model", event.target.value)}
            />
          </SettingsField>

          <SettingsField
            id="settings-api-key"
            label="API key"
            hint="Stored locally in storage/app_settings.json and never sent anywhere except the endpoint above."
            badge={
              settings?.llm_api_key_set ? (
                <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-200">
                  Key saved {settings.llm_api_key_masked}
                </span>
              ) : (
                <span className="rounded-full border border-navy-700/60 bg-navy-850/60 px-2 py-0.5 text-[10px] font-medium text-navy-300">
                  No key set
                </span>
              )
            }
          >
            <input
              id="settings-api-key"
              type="password"
              spellCheck={false}
              autoComplete="off"
              placeholder={
                settings?.llm_api_key_set
                  ? "Leave blank to keep the saved key"
                  : "sk-…"
              }
              className={controlClass(false)}
              value={draft.llm_api_key}
              disabled={isBusy}
              onChange={(event) => setField("llm_api_key", event.target.value)}
            />
          </SettingsField>

          <SettingsField
            id="settings-context-window"
            label="Context window (tokens)"
            error={windowError}
            hint="Used to size image uploads and cap the reply, so a request never overruns the model's window."
          >
            <input
              id="settings-context-window"
              type="number"
              inputMode="numeric"
              min={settings?.bounds.min_context_window}
              max={settings?.bounds.max_context_window}
              step={1024}
              className={controlClass(!!windowError)}
              value={draft.llm_context_window}
              disabled={isBusy}
              onChange={(event) =>
                setField("llm_context_window", event.target.value)
              }
            />
            <div className="flex flex-wrap gap-1.5 pt-1">
              {WINDOW_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  disabled={isBusy}
                  onClick={() =>
                    setField("llm_context_window", String(preset.value))
                  }
                  className="rounded-md border border-navy-700/60 bg-navy-850/50 px-2 py-0.5 text-[10px] font-medium text-navy-300 transition-colors hover:border-accent-500/50 hover:text-accent-200 disabled:opacity-50"
                >
                  {preset.label}
                </button>
              ))}
            </div>
          </SettingsField>

          {settings ? (
            <SettingsNotice tone="info" title="Effective configuration">
              <p>
                {settings.effective_model} at {settings.effective_base_url}
                {settings.llm_api_key_set ? "" : " · no API key"}
              </p>
              <p className="text-navy-300">
                {settings.effective_context_window.toLocaleString()}-token window ·
                images sent at {settings.effective_image_max_dim}px long edge
              </p>
            </SettingsNotice>
          ) : null}

          {error ? (
            <SettingsNotice tone="error" title="Something went wrong">
              {error}
            </SettingsNotice>
          ) : null}

          {testResult ? (
            testResult.ok ? (
              <SettingsNotice tone="success" title="Connection successful">
                <p className="flex items-center gap-1.5">
                  <Sparkles className="h-3 w-3" aria-hidden />
                  {testResult.model} replied: {testResult.reply || "ok"}
                </p>
              </SettingsNotice>
            ) : (
              <SettingsNotice tone="error" title="Connection failed">
                {testResult.error}
              </SettingsNotice>
            )
          ) : isTesting ? (
            <SettingsNotice tone="busy" title="Testing the endpoint…" />
          ) : null}
        </div>
      )}
    </Modal>
  );
}

export default SettingsModal;
