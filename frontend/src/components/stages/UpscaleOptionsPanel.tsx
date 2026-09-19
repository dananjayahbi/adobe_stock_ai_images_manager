"use client";

/**
 * The Stage 3 options panel.
 *
 * Upscaling is the only stage whose result depends on a set of choices the
 * operator has to make (which network, how big, on which GPU), so it gets a
 * dedicated panel rather than the single button the other stages use. The model
 * list is fetched from the server, which reads it off disk, so a new
 * `.bin`/`.param` pair shows up here without a code change.
 *
 * Every control is disabled while a batch is running: the options are read once
 * at the start of a run, so letting them change mid-batch would show a
 * configuration that is not the one being applied.
 */

import {
  AlertTriangle,
  ChevronDown,
  Cpu,
  Gauge,
  Image as ImageIcon,
  Layers,
  Sparkles,
  Zap,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  estimateUpscale,
  fetchGpuDevices,
  fetchUpscaleCatalog,
  formatCapacity,
  formatMegapixels,
  SINGLE_GPU_FALLBACK,
  type GpuList,
  type UpscaleCatalog,
  type UpscaleEstimate,
  type UpscaleModel,
  type UpscaleOptions,
} from "@/lib/upscale";

interface UpscaleOptionsPanelProps {
  /** Current configuration, owned by the workspace. */
  value: UpscaleOptions;
  onChange: (next: UpscaleOptions) => void;
  /** Record whose dimensions drive the live estimate, if one is selected. */
  sampleRecordId?: string | null;
  /** Dimensions to use when no record is selected. */
  sampleDimensions?: { width: number; height: number } | null;
  disabled?: boolean;
}

/** Group models by their source folder, preserving the server's ordering. */
function groupModels(
  models: UpscaleModel[],
  sources: Record<string, string>
): { source: string; label: string; models: UpscaleModel[] }[] {
  const groups = new Map<string, UpscaleModel[]>();
  for (const model of models) {
    const bucket = groups.get(model.source) ?? [];
    bucket.push(model);
    groups.set(model.source, bucket);
  }
  return [...groups.entries()].map(([source, group]) => ({
    source,
    label: sources[source] ?? source,
    models: group,
  }));
}

export default function UpscaleOptionsPanel({
  value,
  onChange,
  sampleRecordId,
  sampleDimensions,
  disabled = false,
}: UpscaleOptionsPanelProps) {
  const [catalog, setCatalog] = useState<UpscaleCatalog | null>(null);
  const [gpus, setGpus] = useState<GpuList>(SINGLE_GPU_FALLBACK);
  const [error, setError] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<UpscaleEstimate | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const estimateRequest = useRef(0);

  useEffect(() => {
    let cancelled = false;
    fetchUpscaleCatalog()
      .then((data) => {
        if (!cancelled) setCatalog(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // The device list is enumerated server-side. A failure is not fatal: the
  // fallback keeps a usable picker rather than an empty one, so the panel still
  // works when the API is briefly unreachable.
  useEffect(() => {
    let cancelled = false;
    fetchGpuDevices()
      .then((data) => {
        if (cancelled || data.devices.length === 0) return;
        setGpus(data);
        // A configured index can point at a device this machine does not have,
        // which would make the CLI fail on every run. Snap it to a real one.
        if (!data.devices.some((device) => device.id === value.gpu_id)) {
          onChange({ ...value, gpu_id: data.default_gpu_id });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // Intentionally runs once: the list is machine state, not user state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-estimate whenever the geometry-affecting inputs change. The request id
  // guards against an older, slower response overwriting a newer one.
  useEffect(() => {
    const width = sampleRecordId ? undefined : sampleDimensions?.width;
    const height = sampleRecordId ? undefined : sampleDimensions?.height;
    if (!sampleRecordId && (!width || !height)) {
      setEstimate(null);
      return;
    }

    const id = ++estimateRequest.current;
    const timer = window.setTimeout(() => {
      estimateUpscale({
        recordId: sampleRecordId ?? undefined,
        width,
        height,
        options: {
          model: value.model,
          model_scale: value.model_scale,
          target_long_edge: value.target_long_edge,
          gpu_id: value.gpu_id,
          tta: value.tta,
          allow_downscale: value.allow_downscale,
        },
      })
        .then((data) => {
          if (estimateRequest.current === id) setEstimate(data);
        })
        .catch(() => {
          if (estimateRequest.current === id) setEstimate(null);
        });
    }, 250);

    return () => window.clearTimeout(timer);
  }, [
    sampleRecordId,
    sampleDimensions?.width,
    sampleDimensions?.height,
    value.model,
    value.model_scale,
    value.target_long_edge,
    value.gpu_id,
    value.tta,
    value.allow_downscale,
  ]);

  const patch = useCallback(
    (partial: Partial<UpscaleOptions>) => onChange({ ...value, ...partial }),
    [onChange, value]
  );

  const groups = useMemo(
    () => (catalog ? groupModels(catalog.models, catalog.sources) : []),
    [catalog]
  );

  const selectedModel = catalog?.models.find((m) => m.name === value.model);
  const devices = gpus.devices;
  const gpu = devices.find((device) => device.id === value.gpu_id);
  const isDiscrete = gpu?.kind === "dedicated";
  const warnings = estimate?.warnings ?? [];

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
        Could not load the Upscayl model catalog: {error}
      </div>
    );
  }

  if (!catalog) {
    return (
      <div className="h-24 animate-pulse rounded-xl border border-navy-800 bg-navy-900/40" />
    );
  }

  return (
    <div className="space-y-4 rounded-xl border border-navy-800 bg-navy-900/60 p-4">
      {!catalog.neural_available && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            The Upscayl CLI was not found, so images will be resampled with
            Lanczos instead of a neural model. Set <code>UPSCAYL_EXE</code> to the
            headless binary to enable neural upscaling.
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* ---------------------------------------------------------------- */}
        {/* Model                                                            */}
        {/* ---------------------------------------------------------------- */}
        <div className="space-y-2">
          <label
            htmlFor="upscale-model"
            className="flex items-center gap-1.5 text-xs font-medium text-navy-300"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Model
            {selectedModel?.recommended && (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                Recommended
              </span>
            )}
          </label>

          <select
            id="upscale-model"
            value={value.model}
            disabled={disabled}
            onChange={(event) => {
              const next = catalog.models.find((m) => m.name === event.target.value);
              patch({
                model: event.target.value,
                model_scale: next?.scale ?? value.model_scale,
              });
            }}
            className="w-full rounded-md border border-navy-700 bg-navy-950 px-2.5 py-2 text-sm text-navy-100 outline-none focus:border-accent-500 disabled:opacity-50"
          >
            {groups.map((group) => (
              <optgroup key={group.source} label={group.label}>
                {group.models.map((model) => (
                  <option key={model.name} value={model.name}>
                    {model.label} · {model.scale}x
                    {model.recommended ? " ★" : ""}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>

          {selectedModel && (
            <p className="text-xs leading-relaxed text-navy-400">
              {selectedModel.description}
            </p>
          )}
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Capacity                                                         */}
        {/* ---------------------------------------------------------------- */}
        <div className="space-y-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-navy-300">
            <Gauge className="h-3.5 w-3.5" />
            Upscale capacity
            <span className="ml-auto text-[10px] font-normal text-navy-400">
              long edge
            </span>
          </span>

          <div className="flex flex-wrap gap-1.5">
            {catalog.resolutions.map((preset) => {
              const active = preset.long_edge === value.target_long_edge;
              return (
                <button
                  key={preset.long_edge}
                  type="button"
                  disabled={disabled}
                  onClick={() => patch({ target_long_edge: preset.long_edge })}
                  aria-pressed={active}
                  className={`rounded-md border px-2.5 py-1.5 text-xs font-medium tabular-nums transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    active
                      ? "border-accent-500 bg-accent-500/15 text-accent-200"
                      : "border-navy-700 bg-navy-800/60 text-navy-300 hover:bg-navy-700"
                  }`}
                >
                  {formatCapacity(preset.long_edge)}
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 text-xs text-navy-400">
            <input
              type="range"
              min={catalog.presets.min_target_long_edge}
              max={catalog.presets.max_target_long_edge}
              step={128}
              value={value.target_long_edge}
              disabled={disabled}
              onChange={(event) =>
                patch({ target_long_edge: Number(event.target.value) })
              }
              aria-label="Custom long edge in pixels"
              className="h-1 flex-1 accent-accent-500"
            />
            <span className="w-20 shrink-0 text-right tabular-nums text-navy-300">
              {value.target_long_edge} px
            </span>
          </div>

          <label className="flex items-center gap-2 text-xs text-navy-400">
            <input
              type="checkbox"
              checked={value.allow_downscale}
              disabled={disabled}
              onChange={(event) => patch({ allow_downscale: event.target.checked })}
              className="h-3.5 w-3.5 accent-accent-500"
            />
            Downscale sources that already exceed the target
          </label>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* GPU                                                              */}
        {/* ---------------------------------------------------------------- */}
        <div className="space-y-2">
          <label
            htmlFor="upscale-gpu"
            className="flex items-center gap-1.5 text-xs font-medium text-navy-300"
          >
            <Cpu className="h-3.5 w-3.5" />
            GPU acceleration
            {isDiscrete && (
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                Dedicated
              </span>
            )}
            {!gpus.available && (
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">
                Unverified
              </span>
            )}
          </label>

          <select
            id="upscale-gpu"
            value={value.gpu_id}
            disabled={disabled}
            onChange={(event) => patch({ gpu_id: Number(event.target.value) })}
            className="w-full rounded-md border border-navy-700 bg-navy-950 px-2.5 py-2 text-sm text-navy-100 outline-none focus:border-accent-500 disabled:opacity-50"
          >
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                [{device.id}] {device.name} · {device.kind_label.toLowerCase()}
              </option>
            ))}
          </select>

          <p className="text-xs text-navy-400">
            {!gpus.available
              ? "The device list could not be read from the upscaler, so these are the expected defaults."
              : isDiscrete
                ? `${gpu?.name} is the discrete GPU. Integrated devices are far slower and are only worth selecting if it is busy.`
                : "No discrete GPU was found. Integrated devices are much slower, so expect long runs."}
          </p>
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Quality toggles                                                  */}
        {/* ---------------------------------------------------------------- */}
        <div className="space-y-2">
          <span className="flex items-center gap-1.5 text-xs font-medium text-navy-300">
            <Layers className="h-3.5 w-3.5" />
            Quality
          </span>

          <label className="flex cursor-pointer items-start gap-2 rounded-md border border-navy-800 bg-navy-950/50 px-2.5 py-2">
            <input
              type="checkbox"
              checked={value.tta}
              disabled={disabled}
              onChange={(event) => patch({ tta: event.target.checked })}
              className="mt-0.5 h-3.5 w-3.5 accent-accent-500"
            />
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-xs font-medium text-navy-200">
                <Zap className="h-3 w-3 text-amber-400" />
                TTA mode
              </span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-navy-400">
                Test-time augmentation. Slightly cleaner edges at roughly double
                the runtime. Best kept off for large batches.
              </span>
            </span>
          </label>

          <div className="flex items-center gap-2 rounded-md border border-navy-800 bg-navy-950/50 px-2.5 py-2">
            <ImageIcon className="h-3.5 w-3.5 shrink-0 text-navy-400" />
            <span className="text-xs text-navy-300">
              Output format
              <span className="ml-2 rounded bg-navy-800 px-1.5 py-0.5 font-mono text-[10px] uppercase text-navy-200">
                {catalog.presets.forced_format}
              </span>
              <span className="ml-2 text-[11px] text-navy-400">
                Adobe Stock accepts JPEG only.
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Live estimate                                                       */}
      {/* ------------------------------------------------------------------ */}
      {estimate && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-navy-800 bg-navy-950/50 px-3 py-2 text-xs">
          <span className="text-navy-400">
            {estimate.source_dimensions[0]}×{estimate.source_dimensions[1]}
            <span className="mx-1.5 text-navy-600">→</span>
            <span className="font-medium text-navy-200">
              {estimate.target_dimensions[0]}×{estimate.target_dimensions[1]}
            </span>
          </span>
          <span className="tabular-nums text-navy-400">
            {estimate.scale.toFixed(2)}× ·{" "}
            {formatMegapixels(estimate.estimated_megapixels)}
          </span>
          {estimate.will_upscale ? (
            <span className="text-emerald-400">neural upscale</span>
          ) : (
            <span className="text-navy-400">kept at native size</span>
          )}
        </div>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1">
          {warnings.map((warning) => (
            <li
              key={warning}
              className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-200"
            >
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* Advanced                                                            */}
      {/* ------------------------------------------------------------------ */}
      <div className="border-t border-navy-800 pt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced((open) => !open)}
          aria-expanded={showAdvanced}
          className="flex items-center gap-1.5 text-xs font-medium text-navy-400 transition-colors hover:text-navy-200"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
          />
          Advanced
        </button>

        {showAdvanced && (
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label
                htmlFor="upscale-tile"
                className="block text-xs font-medium text-navy-300"
              >
                Tile size
              </label>
              <input
                id="upscale-tile"
                type="number"
                min={0}
                step={32}
                value={value.tile_size}
                disabled={disabled}
                onChange={(event) =>
                  patch({ tile_size: Number(event.target.value) })
                }
                className="w-full rounded-md border border-navy-700 bg-navy-950 px-2.5 py-1.5 text-sm text-navy-100 outline-none focus:border-accent-500 disabled:opacity-50"
              />
              <p className="text-[11px] text-navy-400">
                0 lets the CLI choose automatically. Lower values use less VRAM
                but are slower; useful for very large outputs.
              </p>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="upscale-compression"
                className="block text-xs font-medium text-navy-300"
              >
                JPEG quality
                <span className="ml-2 tabular-nums text-navy-400">
                  {value.compression}
                </span>
              </label>
              <input
                id="upscale-compression"
                type="range"
                min={60}
                max={100}
                value={value.compression}
                disabled={disabled}
                onChange={(event) =>
                  patch({ compression: Number(event.target.value) })
                }
                className="h-1 w-full accent-accent-500"
              />
              <p className="text-[11px] text-navy-400">
                90 is a good balance for stock photography. Adobe re-encodes on
                upload, so very high values mostly inflate the file size.
              </p>
            </div>

            <label className="flex items-start gap-2 sm:col-span-2">
              <input
                type="checkbox"
                checked={value.embed_srgb}
                disabled={disabled}
                onChange={(event) => patch({ embed_srgb: event.target.checked })}
                className="mt-0.5 h-3.5 w-3.5 accent-accent-500"
              />
              <span className="text-xs text-navy-300">
                Embed an sRGB colour profile
                <span className="mt-0.5 block text-[11px] text-navy-400">
                  Adobe Stock requires a colour profile on every JPEG. The
                  upscaler writes an untagged file, so this re-encodes it as
                  sRGB. Only disable it if you are embedding a profile yourself
                  later.
                </span>
              </span>
            </label>
          </div>
        )}
      </div>
    </div>
  );
}
