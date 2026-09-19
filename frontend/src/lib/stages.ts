/**
 * Stage pipeline types and metadata.
 *
 * Mirrors `backend/services/stage_registry.py`. Keeping the stage numbering and
 * ordering here lets the workspace render its navigation without a round trip,
 * while `/api/stages` remains the authority if the backend ever changes.
 */

export type PipelineStage =
  | "COLLECTED"
  | "OCR_CLEAR"
  | "OCR_REJECTED"
  | "UPSCALED"
  | "REFINED"
  | "COMPATIBLE"
  | "INCOMPATIBLE"
  | "METADATA_READY"
  | "PUBLISHED";

/** Stage keys accepted by `POST /api/stages/{key}/run`. */
export type StageKey =
  | "ocr"
  | "upscale"
  | "refine"
  | "compatibility"
  | "metadata"
  | "gallery";

export interface StageDefinition {
  number: number;
  key: string;
  name: string;
  description: string;
  stages: PipelineStage[];
  terminal: boolean;
}

export interface StageCount {
  stage: PipelineStage;
  number: number;
  name: string;
  count: number;
}

export interface StageSummary {
  counts: StageCount[];
  total: number;
  ready: number;
  rejected: number;
  incompatible: number;
  average_score: number | null;
}

export type JobItemStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped";

export interface JobItem {
  record_id: string;
  filename: string;
  status: JobItemStatus;
  message: string;
  score: number | null;
  duration_seconds: number | null;
}

export type JobStatus = "running" | "completed" | "failed" | "cancelled";

export interface StageJob {
  id: string;
  stage: string;
  kind: string;
  status: JobStatus;
  message: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  skipped: number;
  progress: number;
  created_at: number;
  finished_at: number | null;
  duration_seconds: number;
  items: JobItem[];
}

export interface AdobeCategory {
  code: number;
  name: string;
}

export interface CsvPreview {
  csv_text: string;
  row_count: number;
  skipped: string[];
  warnings: string[];
}

/** One component of the acceptance score. */
export interface AcceptanceSubScore {
  key: string;
  label: string;
  score: number;
  weight: number;
  issues: AcceptanceIssue[];
}

export interface AcceptanceIssue {
  code: string;
  severity: "critical" | "major" | "minor";
  detail: string;
  value: number | null;
  refinable: boolean;
}

/** The acceptance report persisted on a record by Stage 4/5. */
export interface AcceptanceReport {
  score: number;
  confidence_percent: number;
  threshold: number;
  passed: boolean;
  semantic_included: boolean;
  sub_scores: Record<string, AcceptanceSubScore>;
  issues: AcceptanceIssue[];
  refinable_codes: string[];
  blocking_codes: string[];
  metrics: Record<string, number>;
}

/** Per-stage detail blobs stored on `stage_details`. */
export interface OcrDetail {
  text_detected: boolean;
  classification: "none" | "gibberish" | "embedded_text" | "skipped";
  text: string;
  mean_confidence: number;
  word_count: number;
  reason: string;
  blocked: boolean;
  words: { text: string; confidence: number }[];
}

export interface UpscaleDetail {
  success: boolean;
  output_path: string | null;
  backend: string;
  scale: number;
  source_megapixels: number;
  output_megapixels: number;
  reason: string;
}

export interface RefineDetail {
  success: boolean;
  passes: number;
  initial_score: number;
  final_score: number;
  improved: boolean;
  reason: string;
  history: {
    pass: number;
    score: number;
    note?: string;
    operations?: { operation: string; strength: number; reason: string }[];
    unaddressable?: string[];
  }[];
}

export interface CompatibilityDetail {
  passed: boolean;
  score: number;
  confidence_percent: number;
  threshold: number;
  summary: string;
  remediation: string[];
}

export interface StageDetails {
  ocr?: OcrDetail;
  upscale?: UpscaleDetail;
  refine?: RefineDetail;
  compatibility?: CompatibilityDetail;
  metadata?: { keyword_count: number; category: number | null; generated_at: string };
  publish?: { published_at: string };
}

/** Which stages a given stage key advances a record out of. */
export const STAGE_ENTRY_STAGES: Record<StageKey, PipelineStage[]> = {
  ocr: ["COLLECTED"],
  upscale: ["OCR_CLEAR"],
  refine: ["UPSCALED"],
  compatibility: ["REFINED"],
  metadata: ["COMPATIBLE"],
  gallery: ["METADATA_READY"],
};

/** Fallback registry, used before `/api/stages` responds. */
export const STAGE_DEFINITIONS: StageDefinition[] = [
  {
    number: 1,
    key: "collector",
    name: "Collector",
    description: "AI-generated images saved locally, waiting for an OCR sweep.",
    stages: ["COLLECTED"],
    terminal: false,
  },
  {
    number: 2,
    key: "ocr",
    name: "OCR Detector",
    description:
      "Scans for embedded text. Text found removes the image from the pipeline.",
    stages: ["OCR_CLEAR", "OCR_REJECTED"],
    terminal: false,
  },
  {
    number: 3,
    key: "upscale",
    name: "Upscale",
    description: "Raises resolution to the Adobe Stock megapixel target.",
    stages: ["UPSCALED"],
    terminal: false,
  },
  {
    number: 4,
    key: "refine",
    name: "Image Refiner",
    description:
      "Applies corrective adjustments until the acceptance score clears 80%.",
    stages: ["REFINED"],
    terminal: false,
  },
  {
    number: 5,
    key: "compatibility",
    name: "Compatibility Check",
    description:
      "Runs the full acceptance algorithm and gates at the 80% threshold.",
    stages: ["COMPATIBLE", "INCOMPATIBLE"],
    terminal: false,
  },
  {
    number: 6,
    key: "metadata",
    name: "Metadata & CSV",
    description:
      "Generates titles, descriptions, keywords, and the Adobe Stock CSV.",
    stages: ["METADATA_READY"],
    terminal: false,
  },
  {
    number: 7,
    key: "gallery",
    name: "Gallery",
    description: "Upload-ready assets at 80%+ confidence.",
    stages: ["PUBLISHED"],
    terminal: true,
  },
];

/** Stages that end automated processing. */
export const TERMINAL_STAGES: PipelineStage[] = [
  "OCR_REJECTED",
  "INCOMPATIBLE",
];

/** Per-stage accent colours, used for badges and progress rails. */
export const STAGE_COLORS: Record<PipelineStage, string> = {
  COLLECTED: "text-zinc-300 bg-zinc-500/15 border-zinc-500/40",
  OCR_CLEAR: "text-sky-300 bg-sky-500/15 border-sky-500/40",
  OCR_REJECTED: "text-red-300 bg-red-500/15 border-red-500/40",
  UPSCALED: "text-cyan-300 bg-cyan-500/15 border-cyan-500/40",
  REFINED: "text-violet-300 bg-violet-500/15 border-violet-500/40",
  COMPATIBLE: "text-emerald-300 bg-emerald-500/15 border-emerald-500/40",
  INCOMPATIBLE: "text-amber-300 bg-amber-500/15 border-amber-500/40",
  METADATA_READY: "text-fuchsia-300 bg-fuchsia-500/15 border-fuchsia-500/40",
  PUBLISHED: "text-blue-300 bg-blue-500/15 border-blue-500/40",
};

/** Human-readable label for a stage value. */
export function stageLabel(stage: PipelineStage): string {
  const definition = STAGE_DEFINITIONS.find((d) => d.stages.includes(stage));
  if (!definition) return stage;
  // Sub-states read better with their own wording than the stage's name.
  if (stage === "OCR_REJECTED") return "OCR Rejected";
  if (stage === "INCOMPATIBLE") return "Incompatible";
  return definition.name;
}

/** Stage number (1-7) for a stage value. */
export function stageNumber(stage: PipelineStage): number {
  return STAGE_DEFINITIONS.find((d) => d.stages.includes(stage))?.number ?? 0;
}

/** True when a stage ends automated processing. */
export function isTerminalStage(stage: PipelineStage): boolean {
  return TERMINAL_STAGES.includes(stage);
}

/** Confidence band used for score colouring: >=80% is the acceptance gate. */
export function scoreTone(score: number | null): "good" | "warn" | "bad" | "none" {
  if (score === null || score === undefined) return "none";
  if (score >= 0.8) return "good";
  if (score >= 0.65) return "warn";
  return "bad";
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${(score * 100).toFixed(1)}%`;
}
