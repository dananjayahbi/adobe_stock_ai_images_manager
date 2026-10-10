/**
 * Client-side mirror of the backend step catalog.
 *
 * The server's `GET /api/batches/steps` is authoritative (the UI fetches it);
 * this module holds the same canonical order and per-step config field
 * definitions so the config forms render without a round-trip and tests can
 * assert against a local constant. If the two ever disagree, the server wins:
 * `normaliseSteps` output is what gets stored.
 */
import type { MediaType, StepConfig, StepDefinition } from "./types";

/**
 * Canonical execution order — must match pipeline_defs.STEP_ORDER.
 *
 * Upscale leads so background removal masks an already-upscaled image: a
 * super-resolution pass *after* matting resamples the alpha channel and is
 * what leaves stair-stepped, haloed edges.
 */
export const STEP_ORDER = [
  "upscale",
  "bg_remove",
  "ocr",
  "refine",
  "compatibility",
  "metadata",
] as const;

/** Steps pickable per media type — must match pipeline_defs.STEP_MEDIA_TYPES. */
export const MEDIA_STEPS: Record<MediaType, string[]> = {
  raster: ["ocr", "upscale", "refine", "compatibility", "metadata"],
  png: ["upscale", "bg_remove", "ocr", "metadata"],
};

interface FieldDef {
  /** Config key — always a plain string (StepConfig's index signature makes
   *  `keyof StepConfig` include `number`, which poisons downstream calls). */
  key: string;
  label: string;
  type: "number" | "select" | "toggle";
  options?: { value: string | number | boolean; label: string }[];
  min?: number;
  max?: number;
  step?: number;
  hint?: string;
}

/** Config fields the processing page renders, per step. */
export const STEP_FIELDS: Record<string, FieldDef[]> = {
  bg_remove: [
    {
      key: "gpu",
      label: "Run on GPU (CUDA)",
      type: "toggle",
      hint: "Segmentation on the CUDA provider. Falls back to CPU automatically if CUDA is unavailable.",
    },
    {
      key: "model",
      label: "Model",
      type: "select",
      options: [
        { value: "birefnet-general", label: "BiRefNet General (fine edges)" },
        { value: "birefnet-massive", label: "BiRefNet Massive (most detail)" },
        { value: "birefnet-general-lite", label: "BiRefNet Lite (fast)" },
        { value: "bria-rmbg", label: "BRIA RMBG (commercial cut-outs)" },
        { value: "isnet-general-use", label: "ISNet General" },
        { value: "u2net", label: "U²-Net (fastest)" },
      ],
      hint: "BiRefNet keeps hair-thin antennae and root hairs that SOD models sever.",
    },
    {
      key: "matting",
      label: "Boundary matting",
      type: "select",
      options: [
        { value: "guided", label: "Guided (sub-pixel, offline)" },
        { value: "vitmatte", label: "ViTMatte (neural, needs transformers)" },
        { value: "off", label: "Off (raw mask)" },
      ],
      hint: "Rebuilds the transition band from an auto-trimap for true sub-pixel alpha.",
    },
    {
      key: "defringe",
      label: "Defringe edge colour",
      type: "toggle",
      hint: "Un-blends the old backdrop's colour out of the soft edge (kills halos).",
    },
    {
      key: "sanitize",
      label: "Sanitise alpha",
      type: "toggle",
      hint: "0.5px choke, alpha < 8 → 0, and stray-island removal.",
    },
    {
      key: "edge_check",
      label: "Check edge quality after removal",
      type: "toggle",
      hint: "Stress-tests the cut-out on pure white and pure black and scores jaggedness and halo.",
    },
  ],
  ocr: [],
  upscale: [
    {
      key: "target_long_edge",
      label: "Target long edge (px)",
      type: "number",
      min: 512,
      max: 8192,
      step: 64,
      hint: "3840 ≈ Adobe's 4K / ~8 MP comfort zone.",
    },
    {
      key: "gpu_id",
      label: "GPU",
      type: "number",
      min: 0,
      max: 7,
      hint: "0 is the dedicated card on this machine.",
    },
    {
      key: "tta",
      label: "Test-time augmentation",
      type: "toggle",
      hint: "Slower, marginally cleaner.",
    },
  ],
  refine: [
    {
      key: "use_semantic",
      label: "Include semantic audit",
      type: "toggle",
      hint: "Asks the vision model to weigh in before correcting.",
    },
  ],
  compatibility: [
    {
      key: "use_semantic",
      label: "Include semantic audit",
      type: "toggle",
      hint: "Adds the model's judgement to the 80% gate.",
    },
  ],
  metadata: [
    {
      key: "delay_seconds",
      label: "Delay between calls (s)",
      type: "number",
      min: 0,
      max: 30,
      step: 0.5,
      hint: "Pauses between images to stay under rate limits.",
    },
  ],
};

/** Labels for steps, used where a full StepDefinition is not in scope. */
export const STEP_LABELS: Record<string, string> = {
  bg_remove: "Background removal",
  ocr: "OCR scan",
  upscale: "Upscale",
  refine: "Refine",
  compatibility: "Acceptance QC",
  metadata: "Metadata & keywords",
};

export const STEP_BLURBS: Record<string, string> = {
  bg_remove: "Segments, mattes, defringes and audits the cut-out on both canvases.",
  ocr: "Scans for embedded text (text = rejection).",
  upscale: "Raises resolution to the Adobe target — runs before masking.",
  refine: "Corrective adjustments until the score clears 80%.",
  compatibility: "Full acceptance algorithm, gates at 80%.",
  metadata: "Titles, description, keywords, category.",
};

/** Sort a step list into canonical order (server re-does this; belt + braces). */
export function canonicalOrder(keys: string[]): string[] {
  return [...keys].sort(
    (a, b) => STEP_ORDER.indexOf(a as never) - STEP_ORDER.indexOf(b as never)
  );
}

/** Default config per step — mirrors pipeline_defs.default_step_config. */
export function defaultConfig(key: string): StepConfig {
  switch (key) {
    case "bg_remove":
      return {
        gpu: true,
        model: "birefnet-general",
        matting: "guided",
        defringe: true,
        sanitize: true,
        edge_check: true,
      };
    case "upscale":
      return { model: "4xNomos8kSC", target_long_edge: 3840, gpu_id: 0, tta: false };
    case "refine":
    case "compatibility":
      return { use_semantic: true };
    case "metadata":
      return { delay_seconds: 2 };
    default:
      return {};
  }
}

export function stepDefinition(key: string, mediaType: MediaType): StepDefinition {
  return {
    key,
    label: STEP_LABELS[key] ?? key,
    description: STEP_BLURBS[key] ?? "",
    media_types: key === "bg_remove" ? ["png"] : ["raster", "png"],
    default_config: defaultConfig(key),
  };
}
