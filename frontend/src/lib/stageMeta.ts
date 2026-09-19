/**
 * Presentation metadata for each stage.
 *
 * `lib/stages.ts` holds the *type contract* (mirroring the backend registry);
 * this module holds everything that is purely about how a stage is presented
 * and navigated — route slugs, icons, action copy, and bucket definitions.
 *
 * Keeping the two apart means a copy change never touches the API contract.
 */

import {
  CheckCircle2,
  Database,
  Images,
  Maximize2,
  ScanText,
  SlidersHorizontal,
  Tags,
  type LucideIcon,
} from "lucide-react";

import type { ImageRecord } from "./api";
import type { PipelineStage, StageKey } from "./stages";

/** The six stage keys the backend can actually run. */
export const RUNNABLE_STAGE_KEYS: StageKey[] = [
  "ocr",
  "upscale",
  "refine",
  "compatibility",
  "metadata",
  "gallery",
];

/** Visual weight of a bucket tab. */
export type BucketTone = "draft" | "primary" | "success" | "danger" | "neutral";

export interface BucketSpec {
  id: string;
  label: string;
  /** One-line explanation shown above the grid. */
  hint: string;
  tone: BucketTone;
  /** True when the record belongs in this bucket. First match wins. */
  match: (record: ImageRecord) => boolean;
}

export interface StageMeta {
  /** Route slug, e.g. `/stages/ocr`. */
  slug: string;
  number: number;
  name: string;
  /** Short sentence shown under the page title. */
  tagline: string;
  icon: LucideIcon;
  /**
   * Label for the stage's primary action. `null` for the Collector, which has
   * no server-side runner — its action is uploading.
   */
  action: string | null;
  actionHint: string;
  /** Where records go after this stage. `null` for the terminal stage. */
  next: StageKey | null;
  /** Copy for the "push forward" button. */
  pushLabel: string | null;
  buckets: BucketSpec[];
}

/** The stage value(s) a record may hold while it is *sitting in* a stage. */
const STAGE_VALUES: Record<StageKey, PipelineStage[]> = {
  ocr: ["OCR_CLEAR", "OCR_REJECTED"],
  upscale: ["UPSCALED"],
  refine: ["REFINED"],
  compatibility: ["COMPATIBLE", "INCOMPATIBLE"],
  metadata: ["METADATA_READY"],
  gallery: ["PUBLISHED"],
};

/** True when a record has been pushed into this stage but not yet run. */
export function isDraftFor(record: ImageRecord, key: StageKey): boolean {
  return record.queued_stage === key;
}

/** Pipeline position of a stage key, or -1 when the value is not a stage key. */
export function stageOrder(key: string | null | undefined): number {
  if (!key) return -1;
  return RUNNABLE_STAGE_KEYS.indexOf(key as StageKey);
}

/**
 * The records a stage page should display.
 *
 * A record belongs to a stage while it is either queued there (its *draft*) or
 * sitting on one of the stage's own verdict values.
 *
 * Crucially, a record pushed *onward* leaves the stage it came from. The push
 * only sets `queued_stage`; it cannot rewrite `stage`, because the record has
 * genuinely been processed and that verdict is still its history. Without the
 * explicit exclusion below, the record would satisfy both rules at once and
 * appear in two stages simultaneously — the operator would "move" an image and
 * still see it sitting in the stage they moved it out of.
 */
export function poolFor(records: ImageRecord[], key: StageKey): ImageRecord[] {
  const values = STAGE_VALUES[key];
  const here = stageOrder(key);

  return records.filter((record) => {
    if (isDraftFor(record, key)) return true;
    // Queued for a later stage: it has left this one.
    if (stageOrder(record.queued_stage) > here) return false;
    return values.includes(record.stage);
  });
}

function draftBucket(key: StageKey, label: string, hint: string): BucketSpec {
  return {
    id: "draft",
    label,
    hint,
    tone: "draft",
    match: (record) => isDraftFor(record, key),
  };
}

function primaryBucket(key: StageKey, label: string, hint: string): BucketSpec {
  const values = STAGE_VALUES[key];
  return {
    id: "primary",
    label,
    hint,
    tone: "primary",
    match: (record) => !isDraftFor(record, key) && values.includes(record.stage),
  };
}

/**
 * Bucket definitions per stage.
 *
 * Every stage gets a **Draft** bucket — that is the queue the operator pushed
 * into and has not run yet. The remaining buckets are the stage's own verdict
 * states, so the operator always knows *why* a record sits where it does.
 */
function buildBuckets(key: StageKey): BucketSpec[] {
  switch (key) {
    case "ocr":
      return [
        draftBucket("ocr", "Draft", "Pushed here, not scanned yet."),
        {
          id: "clear",
          label: "Clear",
          hint: "No embedded text found — safe to advance.",
          tone: "success",
          match: (record) => record.stage === "OCR_CLEAR",
        },
        {
          id: "rejected",
          label: "Rejected",
          hint: "Embedded text detected — excluded from the pipeline.",
          tone: "danger",
          match: (record) => record.stage === "OCR_REJECTED",
        },
      ];

    case "compatibility":
      return [
        draftBucket(
          "compatibility",
          "Draft",
          "Pushed here, acceptance check not run yet."
        ),
        {
          id: "compatible",
          label: "Compatible",
          hint: "Cleared the 80% acceptance threshold.",
          tone: "success",
          match: (record) => record.stage === "COMPATIBLE",
        },
        {
          id: "incompatible",
          label: "Incompatible",
          hint: "Below threshold — needs refining or removal.",
          tone: "danger",
          match: (record) => record.stage === "INCOMPATIBLE",
        },
      ];

    case "gallery":
      return [
        draftBucket(
          "gallery",
          "Ready to publish",
          "Pushed here, not published to the gallery yet."
        ),
        {
          id: "published",
          label: "Published",
          hint: "Upload-ready assets.",
          tone: "success",
          match: (record) => record.stage === "PUBLISHED",
        },
      ];

    case "upscale":
      return [
        draftBucket("upscale", "Draft", "Pushed here, resolution not raised yet."),
        primaryBucket("upscale", "Upscaled", "Resolution raised to the target."),
      ];

    case "refine":
      return [
        draftBucket("refine", "Draft", "Pushed here, not refined yet."),
        primaryBucket("refine", "Refined", "Corrective passes applied."),
      ];

    case "metadata":
      return [
        draftBucket("metadata", "Draft", "Pushed here, metadata not generated yet."),
        primaryBucket("metadata", "Metadata ready", "Title, description and keywords set."),
      ];
  }
}

/**
 * Collector buckets.
 *
 * The Collector is the only stage whose pool is *every* record, so its buckets
 * have to distinguish three genuinely different situations: uploaded and idle,
 * uploaded and pushed, and already past OCR (which the operator now manages from
 * the OCR page onward).
 */
const COLLECTOR_BUCKETS: BucketSpec[] = [
  {
    id: "inbox",
    label: "In Collector",
    hint: "Uploaded and waiting. Select some and push them to the OCR Detector.",
    tone: "primary",
    match: (record) => record.stage === "COLLECTED" && record.queued_stage !== "ocr",
  },
  {
    id: "pushed",
    label: "Pushed to OCR",
    hint: "Queued for the OCR Detector — open that page to scan them.",
    tone: "draft",
    match: (record) => record.stage === "COLLECTED" && record.queued_stage === "ocr",
  },
  {
    id: "advanced",
    label: "Moved on",
    hint: "Already past OCR — manage these from the later stages.",
    tone: "neutral",
    match: (record) => record.stage !== "COLLECTED",
  },
];

/** Presentation metadata for the Collector — the only stage with no runner. */
export const COLLECTOR_META: StageMeta = {
  slug: "collector",
  number: 1,
  name: "Collector",
  tagline: "Upload AI-generated images and hold them until you are ready.",
  icon: Database,
  action: null,
  actionHint: "Upload images, select the ones you want, then push them to the OCR Detector.",
  next: "ocr",
  pushLabel: "Push to OCR Detector",
  buckets: COLLECTOR_BUCKETS,
};

/** Presentation metadata for a runnable stage. */
export const STAGE_META: Record<StageKey, StageMeta> = {
  ocr: {
    slug: "ocr",
    number: 2,
    name: "OCR Detector",
    tagline: "Scan for embedded text. Anything with text leaves the pipeline.",
    icon: ScanText,
    action: "Scan for text",
    actionHint: "Images containing text are rejected and excluded from the pipeline.",
    next: "upscale",
    pushLabel: "Push to Upscale",
    buckets: buildBuckets("ocr"),
  },
  upscale: {
    slug: "upscale",
    number: 3,
    name: "Upscale",
    tagline: "Raise resolution to the Adobe Stock megapixel target.",
    icon: Maximize2,
    action: "Upscale images",
    actionHint: "Runs the local Upscayl backend on the selected images.",
    next: "refine",
    pushLabel: "Push to Refiner",
    buckets: buildBuckets("upscale"),
  },
  refine: {
    slug: "refine",
    number: 4,
    name: "Image Refiner",
    tagline: "Corrective passes until the acceptance score clears 80%.",
    icon: SlidersHorizontal,
    action: "Auto-refine",
    actionHint: "Applies targeted adjustments based on the last acceptance report.",
    next: "compatibility",
    pushLabel: "Push to Compatibility",
    buckets: buildBuckets("refine"),
  },
  compatibility: {
    slug: "compatibility",
    number: 5,
    name: "Compatibility Check",
    tagline: "Full acceptance algorithm, gated at the 80% threshold.",
    icon: CheckCircle2,
    action: "Run compatibility check",
    actionHint: "Scores each image and records the blocking issues.",
    next: "metadata",
    pushLabel: "Push to Metadata",
    buckets: buildBuckets("compatibility"),
  },
  metadata: {
    slug: "metadata",
    number: 6,
    name: "Metadata & CSV",
    tagline: "Titles, descriptions, keywords, and the Adobe Stock CSV.",
    icon: Tags,
    action: "Generate metadata",
    actionHint: "Uses the configured LLM to write Adobe Stock metadata.",
    next: "gallery",
    pushLabel: "Push to Gallery",
    buckets: buildBuckets("metadata"),
  },
  gallery: {
    slug: "gallery",
    number: 7,
    name: "Gallery",
    tagline: "Publish upload-ready assets at 80%+ confidence.",
    icon: Images,
    action: "Publish to gallery",
    actionHint: "Copies each image to ready-to-upload and embeds the metadata.",
    next: null,
    pushLabel: null,
    buckets: buildBuckets("gallery"),
  },
};

/** Ordered list of every stage, Collector first. */
export const ALL_STAGE_META: StageMeta[] = [
  COLLECTOR_META,
  STAGE_META.ocr,
  STAGE_META.upscale,
  STAGE_META.refine,
  STAGE_META.compatibility,
  STAGE_META.metadata,
  STAGE_META.gallery,
];

/** Look up stage metadata by route slug. */
export function metaForSlug(slug: string): StageMeta | null {
  return ALL_STAGE_META.find((meta) => meta.slug === slug) ?? null;
}

/** The bucket a record belongs to on a given stage page, if any. */
export function bucketFor(
  meta: StageMeta,
  record: ImageRecord
): BucketSpec | undefined {
  return meta.buckets.find((bucket) => bucket.match(record));
}

/** True when the slug names the Collector rather than a runnable stage. */
export function isCollectorSlug(slug: string): boolean {
  return slug === COLLECTOR_META.slug;
}
