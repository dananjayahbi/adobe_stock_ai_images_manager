"use client";

import { Globe, KeyRound } from "lucide-react";

import { SettingsField, controlClass } from "@/components/settings/SettingsField";
import { SettingsNotice } from "@/components/settings/SettingsNotice";
import { cn } from "@/lib/cn";
import type { AppSettings } from "@/lib/settings";
import type { SettingsDraft } from "@/hooks/useAppSettings";

export interface SearchProviderPanelProps {
  settings: AppSettings;
  draft: SettingsDraft;
  setField: <K extends keyof SettingsDraft>(key: K, value: SettingsDraft[K]) => void;
  disabled?: boolean;
  /** The search half of the last probe, when one was run. */
  probe?: {
    ok: boolean;
    provider_label: string;
    results: number;
    error?: string | null;
  } | null;
  className?: string;
}

/**
 * The research agent's web-search provider.
 *
 * Two decisions worth stating:
 *
 * * **The panel reports the *effective* provider, not the toggle.** Brave can be
 *   switched on while no key is stored, and in that state it is not used at all.
 *   Showing "Brave: on" there would be a lie the operator only discovers by
 *   noticing their searches look different — so the badge reads from
 *   `effective_uses_brave` and says plainly when a key is still needed.
 * * **The fallback chain is stated in the copy.** The operator asked for a silent
 *   fallback, and "silent" is only safe if they know it exists. DuckDuckGo is
 *   described as the same *kind* of source (a general index), while Google News is
 *   named as the weaker last resort — which is exactly the distinction the backend
 *   encodes as the evidence tier.
 */
export function SearchProviderPanel({
  settings,
  draft,
  setField,
  disabled = false,
  probe,
  className,
}: SearchProviderPanelProps) {
  const isBusy = Boolean(disabled);
  const needsKey = draft.brave_search_enabled && !settings.brave_search_api_key_set;
  // While a key is being typed the stored flag is still false, so the "needs a
  // key" warning must clear as soon as the field has content — otherwise the
  // operator is told their input does not count.
  const keyProvided =
    settings.brave_search_api_key_set || draft.brave_search_api_key.trim().length > 0;

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-start gap-2.5">
        <span className="mt-px shrink-0 text-accent-300">
          <Globe className="h-3.5 w-3.5" aria-hidden />
        </span>
        <div className="space-y-0.5">
          <h3 className="text-xs font-semibold text-navy-100">Web search</h3>
          <p className="text-[11px] leading-relaxed text-navy-400">
            Where the research agent looks for evidence. These settings apply to
            the next research turn — no restart.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 rounded-lg border border-navy-700/50 bg-navy-850/40 px-3 py-2">
        <span className="text-[11px] text-navy-400">Active provider</span>
        <span
          className={cn(
            "ml-auto rounded-full border px-2 py-0.5 text-[10px] font-medium",
            settings.effective_uses_brave
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
              : "border-navy-700/60 bg-navy-850/60 text-navy-300"
          )}
        >
          {settings.effective_uses_brave ? "Brave Search" : "DuckDuckGo"}
        </span>
      </div>

      <label className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-navy-700/50 bg-navy-850/30 px-3 py-2.5">
        <input
          type="checkbox"
          className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-accent-500"
          checked={draft.brave_search_enabled}
          disabled={isBusy}
          onChange={(event) =>
            setField("brave_search_enabled", event.target.checked)
          }
        />
        <span className="space-y-0.5">
          <span className="block text-[11px] font-medium text-navy-100">
            Use Brave Search first
          </span>
          <span className="block text-[11px] leading-relaxed text-navy-400">
            An indexed JSON API, so results are more reliable than the
            unauthenticated search used otherwise. Needs a Brave Search API key.
          </span>
        </span>
      </label>

      {needsKey && !keyProvided ? (
        <SettingsNotice tone="error" title="A Brave Search API key is required">
          Brave cannot be used without a key, so research would silently stay on
          DuckDuckGo. Paste a key below, or clear this checkbox.
        </SettingsNotice>
      ) : null}

      <SettingsField
        id="settings-brave-key"
        label="Brave Search API key"
        hint="Stored locally in storage/app_settings.json. Sent only to api.search.brave.com."
        badge={
          settings.brave_search_api_key_set ? (
            <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-200">
              Key saved {settings.brave_search_api_key_masked}
            </span>
          ) : (
            <span className="rounded-full border border-navy-700/60 bg-navy-850/60 px-2 py-0.5 text-[10px] font-medium text-navy-300">
              No key set
            </span>
          )
        }
      >
        <div className="relative">
          <KeyRound
            className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-500"
            aria-hidden
          />
          <input
            id="settings-brave-key"
            type="password"
            spellCheck={false}
            autoComplete="off"
            placeholder={
              settings.brave_search_api_key_set
                ? "Leave blank to keep the saved key"
                : "BSA…"
            }
            className={cn(controlClass(false), "pl-8")}
            value={draft.brave_search_api_key}
            disabled={isBusy}
            onChange={(event) =>
              setField("brave_search_api_key", event.target.value)
            }
          />
        </div>
      </SettingsField>

      <SettingsField
        id="settings-brave-rate"
        label="Requests per second"
        hint="How fast your Brave plan allows. Queries are spaced out to avoid a rate-limit error; the fallback covers it if one still happens."
      >
        <input
          id="settings-brave-rate"
          type="number"
          min={settings.bounds.min_brave_rate}
          max={settings.bounds.max_brave_rate}
          step="0.1"
          className={controlClass(false)}
          value={draft.brave_search_rate_limit}
          disabled={isBusy}
          onChange={(event) =>
            setField("brave_search_rate_limit", event.target.value)
          }
        />
      </SettingsField>

      {probe ? (
        <SettingsNotice
          tone={probe.ok ? "success" : "error"}
          title={
            probe.ok
              ? `Search works — answered by ${probe.provider_label}`
              : "Search could not be completed"
          }
        >
          {probe.ok
            ? `${probe.results} result${probe.results === 1 ? "" : "s"} returned.`
            : probe.error}
        </SettingsNotice>
      ) : null}

      <p className="rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2 text-[11px] leading-relaxed text-navy-400">
        If the active provider is unavailable, rate-limited or returns nothing
        usable, the agent falls back automatically: <strong>DuckDuckGo</strong>{" "}
        first (the same kind of general web index, so the switch is silent), then{" "}
        <strong>Google News</strong> as a last resort. News coverage is announced
        in the results, because it shows what is being written about a topic
        rather than how many competing stock images exist.
      </p>
    </div>
  );
}
