/**
 * Stage 3 upscale types and API calls.
 *
 * Kept separate from `lib/api.ts` because the upscaler has its own vocabulary
 * (models, capacities, GPU devices) that only the Stage 3 workspace needs. The
 * model list is never hard-coded on the client: `/api/upscale/catalog` reads it
 * from disk, so dropping a new `.bin`/`.param` pair into a model folder makes it
 * appear in the picker without a frontend change.
 */

import axios from "axios";

import { API_BASE_URL } from "./api";

const api = axios.create({ baseURL: API_BASE_URL, timeout: 30000 });

/** Which folder a model was discovered in. */
export type UpscaleModelSource = "bundled" | "outsourced" | "custom";

/** One selectable ncnn model. */
export interface UpscaleModel {
  name: string;
  label: string;
  /** Native network scale (2, 3 or 4). */
  scale: number;
  source: UpscaleModelSource;
  description: string;
  recommended: boolean;
}

/** A capacity preset offered in the picker. */
export interface ResolutionPreset {
  long_edge: number;
  label: string;
  default: boolean;
}

/** Status of one model folder, so a missing path is visible rather than silent. */
export interface UpscaleDirectory {
  source: UpscaleModelSource;
  path: string;
  exists: boolean;
}

/** The values the options panel should open with. */
export interface UpscaleDefaults {
  target_long_edge: number;
  gpu_id: number;
  model_scale: number;
  tta: boolean;
  tile_size: number;
  compression: number;
  embed_srgb: boolean;
  allow_downscale: boolean;
}

/** Numeric bounds the server enforces, surfaced so the UI can clamp first. */
export interface UpscalePresets {
  tile_auto: number;
  min_tile_size: number;
  min_target_long_edge: number;
  max_target_long_edge: number;
  forced_format: string;
}

/** Everything the Stage 3 panel needs to render itself, in one request. */
export interface UpscaleCatalog {
  models: UpscaleModel[];
  default_model: string;
  sources: Record<string, string>;
  directories: UpscaleDirectory[];
  resolutions: ResolutionPreset[];
  defaults: UpscaleDefaults;
  /** False when the headless binary is missing and only resampling is possible. */
  neural_available: boolean;
  executable: string | null;
  presets: UpscalePresets;
}

/** The full Stage 3 configuration sent with a run request. */
export interface UpscaleOptions {
  model: string;
  model_scale: number;
  target_long_edge: number;
  gpu_id: number;
  tta: boolean;
  tile_size: number;
  compression: number;
  embed_srgb: boolean;
  allow_downscale: boolean;
}

/**
 * Mirror of the server defaults, used only until `/api/upscale/options`
 * responds.
 *
 * The panel's controls are controlled inputs, so they need a complete object to
 * render against. Starting from `null` would blank the panel on every page load;
 * starting from these values means the controls are usable immediately and are
 * then reconciled with whatever the server reports.
 */
export const FALLBACK_UPSCALE_OPTIONS: UpscaleOptions = {
  model: "4xNomos8kSC",
  model_scale: 4,
  target_long_edge: 3840,
  gpu_id: 0,
  tta: false,
  tile_size: 0,
  compression: 90,
  embed_srgb: true,
  allow_downscale: false,
};

/** A Vulkan device the CLI can run on. */
export interface GpuDevice {
  id: number;
  name: string;
  kind: string;
  kind_label: string;
  recommended: boolean;
  details?: Record<string, string>;
}

/** The device list plus the index the server would default to. */
export interface GpuList {
  devices: GpuDevice[];
  default_gpu_id: number;
  available: boolean;
}

/**
 * Known devices on this machine, probed from the CLI's verbose startup header.
 *
 * Only used when {@link fetchGpuDevices} cannot reach the server, so the picker
 * is never empty. The live list comes from `GET /api/upscale/gpus`, which
 * enumerates the real Vulkan adapters - this mirror exists purely as a fallback
 * and is deliberately the common single-GPU-plus-integrated layout.
 */
export const FALLBACK_GPU_DEVICES: GpuDevice[] = [
  {
    id: 0,
    name: "NVIDIA GeForce GTX 1660 Ti",
    kind: "dedicated",
    kind_label: "Dedicated",
    recommended: true,
  },
  {
    id: 1,
    name: "Intel(R) UHD Graphics",
    kind: "integrated",
    kind_label: "Integrated",
    recommended: false,
  },
];

/** A single-device fallback for a machine where enumeration found nothing. */
export const SINGLE_GPU_FALLBACK: GpuList = {
  devices: FALLBACK_GPU_DEVICES,
  default_gpu_id: 0,
  available: false,
};

/**
 * Enumerate the Vulkan devices the upscaler can actually use.
 *
 * The device list is read from the backend rather than hard-coded, so a machine
 * with only an integrated GPU is never offered a discrete device that does not
 * exist, and a workstation with two discrete GPUs can use the second one.
 */
export async function fetchGpuDevices(refresh = false): Promise<GpuList> {
  const { data } = await api.get<GpuList>("/api/upscale/gpus", {
    params: refresh ? { refresh: true } : undefined,
  });
  return data;
}

/** The device to preselect, preferring the server's recommendation. */
export function defaultGpuId(list: GpuList | null, fallback: number): number {
  if (!list || list.devices.length === 0) return fallback;
  if (list.devices.some((device) => device.id === fallback)) return fallback;
  return list.default_gpu_id;
}

/** Predicted output geometry for a configuration, computed before running. */
export interface UpscaleEstimate {
  source_dimensions: [number, number];
  target_dimensions: [number, number];
  scale: number;
  model_scale: number;
  will_upscale: boolean;
  will_downscale: boolean;
  estimated_megapixels: number;
  exceeds_megapixel_ceiling: boolean;
  warnings: string[];
}

export async function fetchUpscaleCatalog(
  refresh = false
): Promise<UpscaleCatalog> {
  const { data } = await api.get<UpscaleCatalog>("/api/upscale/catalog", {
    params: refresh ? { refresh: true } : undefined,
  });
  return data;
}

export async function fetchUpscaleDefaults(): Promise<UpscaleOptions> {
  const { data } = await api.get<UpscaleOptions>("/api/upscale/options");
  return data;
}

/**
 * Ask what a configuration would produce.
 *
 * Pass either a `recordId` (the server measures the file) or explicit
 * dimensions, so the panel can show a live preview as the operator changes the
 * capacity without needing a record selected.
 */
export async function estimateUpscale(params: {
  recordId?: string;
  width?: number;
  height?: number;
  options?: Partial<UpscaleOptions>;
}): Promise<UpscaleEstimate> {
  const { data } = await api.post<UpscaleEstimate>("/api/upscale/estimate", {
    record_id: params.recordId,
    width: params.width,
    height: params.height,
    upscale: params.options,
  });
  return data;
}

/** Format a long edge as the capacity label the picker uses. */
export function formatCapacity(longEdge: number): string {
  if (longEdge % 1000 === 0) return `${longEdge / 1000}K`;
  return `${longEdge} px`;
}

/** Human-readable megapixel figure. */
export function formatMegapixels(megapixels: number): string {
  return `${megapixels.toFixed(1)} MP`;
}
