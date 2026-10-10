"use client";

import { useCallback, useState } from "react";
import Button from "@/components/ui/Button";
import { useSetupStatus } from "@/hooks/useSetupStatus";
import { useSettings } from "@/hooks/useSettings";
import DependencyCard from "@/components/setup/DependencyCard";
import EnvironmentCard from "@/components/setup/EnvironmentCard";
import InstallIndicator from "@/components/setup/InstallIndicator";
import InstallProgressModal from "@/components/setup/InstallProgressModal";
import GatewaySettingsCard from "@/components/settings/GatewaySettingsCard";
import MetadataSettingsCard from "@/components/settings/MetadataSettingsCard";
import ModelStorageCard from "@/components/setup/ModelStorageCard";

/**
 * Config: server-side dependencies (PyTorch, matting stack, ViTMatte
 * weights), model storage, and the Python environment probe.
 *
 * This page owns `useSetupStatus`, so polling and the running-install
 * indicator survive the modal being closed — the modal and the indicator are
 * both pure views of the one shared hook instance. Opening the modal sets
 * local state only; it never starts or stops the job, which runs server-side.
 */
export default function SettingsPage() {
  const {
    status,
    refresh,
    startInstall,
    cancelInstall,
    probeSetup,
    probe,
    probing,
    error,
    busy,
  } = useSetupStatus();
  const [installOpen, setInstallOpen] = useState(false);
  /** Which card fired the in-flight install — scopes its spinner. */
  const [installingKey, setInstallingKey] = useState<string | null>(null);

  // Runtime settings (AI gateway + metadata generation) share one controller:
  // Save/Reset live in this page's action bar, the cards are pure views.
  const settingsController = useSettings();
  const { isSaving, isTesting } = settingsController;

  const running = status?.running ?? false;

  // The modal shows the freshest probe: a result from this session's Run
  // button wins over whatever the last status poll carried.
  const activeProbe = probe ?? status?.probe ?? null;

  const handleInstall = useCallback(
    (groupKey: string) => {
      setInstallOpen(true); // open first — progress appears immediately
      setInstallingKey(groupKey);
      void startInstall([groupKey]).finally(() => setInstallingKey(null));
    },
    [startInstall]
  );

  /** Groups still missing on disk, in server order. */
  const missing = (status?.groups ?? [])
    .filter((group) => !group.installed)
    .map((group) => group.key);

  // The API takes several groups in one request, so "everything" is a single
  // job with a single progress bar rather than three runs in a row.
  const handleInstallAll = useCallback(() => {
    if (missing.length === 0) return;
    setInstallOpen(true);
    setInstallingKey(null);
    void startInstall(missing);
  }, [missing, startInstall]);

  return (
    <div className="space-y-8">
      <InstallIndicator status={status} onOpen={() => setInstallOpen(true)} />

      {/* Header: label + title, then the reference's layered rule lines. */}
      <div>
        <p className="label-caps">Server setup</p>
        <h1 className="mt-1 font-display text-3xl text-ink-800">Config</h1>
        <div className="mt-3 h-px bg-brass-400/50" />
        <div className="mt-[2px] h-px bg-parchment-400" />
      </div>

      {error && (
        <p
          className="cursor-pointer rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
          role="alert"
          onClick={() => void refresh()}
          title="Click to refresh"
        >
          {error}
        </p>
      )}

      {/* Runtime settings — the AI gateway metadata generation talks to, plus
          the generation options themselves. Both save server-side, so a change
          reaches the next request with no restart. */}
      <section aria-label="AI settings">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <p className="label-caps">AI settings</p>
          <div className="flex flex-wrap items-center gap-2">
            {settingsController.notice && (
              <span className="text-xs text-olive-400" role="status">
                {settingsController.notice}
              </span>
            )}
            {settingsController.error && (
              <span className="text-xs text-oxblood-400" role="alert">
                {settingsController.error}
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => void settingsController.reset()}
              disabled={isSaving || isTesting}
              title="Clear saved overrides and fall back to the .env values"
            >
              Reset to defaults
            </Button>
            <Button
              size="sm"
              type="button"
              onClick={() => void settingsController.save()}
              loading={isSaving}
              disabled={isTesting || settingsController.isLoading}
            >
              Save settings
            </Button>
          </div>
        </div>

        {settingsController.isLoading && !settingsController.settings ? (
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="frame-card h-64 animate-pulse bg-parchment-200" />
            <div className="frame-card h-64 animate-pulse bg-parchment-200" />
          </div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            <GatewaySettingsCard controller={settingsController} />
            <MetadataSettingsCard controller={settingsController} />
          </div>
        )}
      </section>

      <section aria-label="Dependencies">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <p className="label-caps">Dependencies</p>
          <div className="flex items-center gap-3">
            <span className="font-stamp text-[11px] text-ink-400">
              {running
                ? "An install is running…"
                : "Installs run on the server"}
            </span>
            {!running && !busy && missing.length > 1 && (
              <Button
                variant="secondary"
                size="sm"
                type="button"
                onClick={handleInstallAll}
              >
                Install all ({missing.length})
              </Button>
            )}
          </div>
        </div>

        {!status && !error && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div
                key={index}
                className="frame-card h-32 animate-pulse bg-parchment-200"
              />
            ))}
          </div>
        )}

        {status && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {status.groups.map((group) => (
              <DependencyCard
                key={group.key}
                group={group}
                running={running}
                busy={busy}
                loading={busy && installingKey === group.key}
                onInstall={() => handleInstall(group.key)}
              />
            ))}
          </div>
        )}
      </section>

      {status && (
        <section
          aria-label="Model storage and environment"
          className="grid gap-6 lg:grid-cols-2"
        >
          <ModelStorageCard models={status.models} />
          <EnvironmentCard
            environment={status.environment}
            probe={activeProbe}
            probing={probing}
            onProbe={() => void probeSetup()}
          />
        </section>
      )}

      <InstallProgressModal
        open={installOpen}
        onClose={() => setInstallOpen(false)}
        status={status}
        error={error}
        onCancel={() => void cancelInstall()}
        cancelBusy={busy}
      />
    </div>
  );
}
