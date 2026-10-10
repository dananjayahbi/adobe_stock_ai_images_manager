"use client";

import type { UseSettingsResult } from "@/hooks/useSettings";

const inputClass =
  "w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60";

interface Props {
  controller: UseSettingsResult;
}

/**
 * The web-search card: Brave Search as the research agent's primary provider,
 * with DuckDuckGo as the automatic fallback when no key is configured.
 *
 * The `effective_*` values are shown rather than the stored ones so the card
 * can never claim Brave is active for an enabled-but-keyless configuration —
 * the backend derives that flag for exactly this reason.
 */
export default function SearchSettingsCard({ controller }: Props) {
  const { settings, draft, isLoading, setField } = controller;

  const provider = settings?.effective_search_provider ?? "duckduckgo";
  const providerLabel =
    provider === "brave" ? "Brave Search (active)" : "DuckDuckGo (fallback)";

  return (
    <section aria-label="Web search" className="frame-card px-5 py-4">
      <p className="label-caps">Web search</p>
      <h2 className="mt-1 font-display text-xl text-ink-800">Search provider</h2>
      <p className="mt-1 text-sm text-ink-400">
        The research agent searches the web through Brave when a key is set, and
        falls back to DuckDuckGo automatically otherwise.
      </p>

      <p
        className="mt-3 inline-flex items-center gap-2 rounded-sm border border-parchment-500 px-2 py-1 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-600"
        title={
          settings?.effective_uses_brave
            ? "A key is stored and Brave will be tried first"
            : "No usable key — searches use DuckDuckGo"
        }
      >
        <span
          className={`h-2 w-2 rounded-full ${
            settings?.effective_uses_brave ? "bg-olive-500" : "bg-rust-500"
          }`}
          aria-hidden="true"
        />
        {providerLabel}
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="flex items-center gap-2 text-sm text-ink-800">
            <input
              type="checkbox"
              checked={draft.brave_search_enabled}
              disabled={isLoading}
              onChange={(event) =>
                setField("brave_search_enabled", event.target.checked)
              }
              className="h-4 w-4 accent-oxblood-500"
            />
            Use Brave Search as the primary provider
          </label>
          {!draft.brave_search_enabled && (
            <p className="mt-1 text-xs text-ink-400">
              Currently searching with DuckDuckGo only.
            </p>
          )}
        </div>

        <div>
          <label htmlFor="set-brave-key" className="label-caps mb-1 block">
            Brave API key
          </label>
          <input
            id="set-brave-key"
            type="password"
            value={draft.brave_search_api_key}
            disabled={isLoading}
            onChange={(event) =>
              setField("brave_search_api_key", event.target.value)
            }
            placeholder={
              settings?.brave_search_api_key_set
                ? `saved (${settings.brave_search_api_key_masked})`
                : "not set"
            }
            autoComplete="off"
            className={inputClass}
          />
          <p className="mt-1 text-xs text-ink-400">
            Leave blank to keep the stored key. Get one at brave.com/search/api.
          </p>
        </div>

        <div>
          <label htmlFor="set-brave-rate" className="label-caps mb-1 block">
            Rate limit (requests / second)
          </label>
          <input
            id="set-brave-rate"
            type="number"
            step="0.1"
            min={settings?.bounds.min_brave_rate}
            max={settings?.bounds.max_brave_rate}
            value={draft.brave_search_rate_limit}
            disabled={isLoading}
            onChange={(event) =>
              setField("brave_search_rate_limit", event.target.value)
            }
            className={inputClass}
          />
          <p className="mt-1 text-xs text-ink-400">
            Paces Brave calls so a research run cannot trip the API quota.
          </p>
        </div>
      </div>
    </section>
  );
}
