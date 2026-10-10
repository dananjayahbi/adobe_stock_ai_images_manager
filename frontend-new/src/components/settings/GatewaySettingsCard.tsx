"use client";

import Button from "@/components/ui/Button";
import type { UseSettingsResult } from "@/hooks/useSettings";

/** Preset context windows covering the common vision models. */
const WINDOW_PRESETS: Array<{ label: string; value: number }> = [
  { label: "8K", value: 8192 },
  { label: "32K", value: 32768 },
  { label: "128K", value: 131072 },
  { label: "200K", value: 200000 },
];

const inputClass =
  "w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60";

interface Props {
  controller: UseSettingsResult;
}

/**
 * The AI gateway card: the OpenAI-compatible endpoint every AI feature
 * (metadata generation, semantic QC) talks to. Stored server-side, so a save
 * takes effect on the next request with no restart.
 */
export default function GatewaySettingsCard({ controller }: Props) {
  const { settings, draft, isLoading, testResult, setField } = controller;

  return (
    <section aria-label="AI gateway" className="frame-card px-5 py-4">
      <p className="label-caps">AI gateway</p>
      <h2 className="mt-1 font-display text-xl text-ink-800">
        Model endpoint
      </h2>
      <p className="mt-1 text-sm text-ink-400">
        Metadata generation and semantic QC go through any OpenAI-compatible
        endpoint. Saved values apply to the very next request.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor="set-base-url" className="label-caps mb-1 block">
            Base URL
          </label>
          <input
            id="set-base-url"
            type="text"
            value={draft.llm_base_url}
            disabled={isLoading}
            onChange={(event) => setField("llm_base_url", event.target.value)}
            placeholder={settings?.defaults.llm_base_url}
            className={inputClass}
          />
          {settings &&
            settings.effective_base_url !== draft.llm_base_url && (
              <p className="mt-1 text-xs text-ink-400">
                Effective now: {settings.effective_base_url}
              </p>
            )}
        </div>

        <div>
          <label htmlFor="set-model" className="label-caps mb-1 block">
            Model ID
          </label>
          <input
            id="set-model"
            type="text"
            value={draft.llm_model}
            disabled={isLoading}
            onChange={(event) => setField("llm_model", event.target.value)}
            placeholder={settings?.defaults.llm_model}
            className={inputClass}
          />
        </div>

        <div>
          <label htmlFor="set-key" className="label-caps mb-1 block">
            API key
          </label>
          <input
            id="set-key"
            type="password"
            value={draft.llm_api_key}
            disabled={isLoading}
            onChange={(event) => setField("llm_api_key", event.target.value)}
            placeholder={
              settings?.llm_api_key_set
                ? `saved (${settings.llm_api_key_masked})`
                : "not set"
            }
            autoComplete="off"
            className={inputClass}
          />
          <p className="mt-1 text-xs text-ink-400">
            Leave blank to keep the stored key.
          </p>
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="set-window" className="label-caps mb-1 block">
            Context window (tokens)
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <input
              id="set-window"
              type="number"
              value={draft.llm_context_window}
              disabled={isLoading}
              min={settings?.bounds.min_context_window}
              max={settings?.bounds.max_context_window}
              onChange={(event) => setField("llm_context_window", event.target.value)}
              className={`${inputClass} max-w-[10rem]`}
            />
            {WINDOW_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                disabled={isLoading}
                onClick={() => setField("llm_context_window", String(preset.value))}
                className="rounded-sm border border-parchment-500 px-2 py-1 font-stamp text-[11px] text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-900 disabled:opacity-60"
              >
                {preset.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => void controller.test()}
          loading={controller.isTesting}
        >
          Test connection
        </Button>
        <span className="text-xs text-ink-400">
          Testing never saves the values you are experimenting with.
        </span>
      </div>

      {testResult && (
        <p
          className={`mt-3 rounded-sm border px-3 py-2 text-sm ${
            testResult.ok
              ? "border-olive-500/60 bg-olive-400/10 text-olive-400"
              : "border-oxblood-500/40 bg-oxblood-400/10 text-oxblood-400"
          }`}
          role="status"
        >
          {testResult.ok
            ? `Connection successful — ${testResult.model ?? "?"}: “${testResult.reply ?? "ok"}”`
            : `Connection failed: ${testResult.error}`}
        </p>
      )}
    </section>
  );
}
