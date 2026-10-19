/** Shared API types for the batch studio (mirrors backend/schemas.py). */

export type MediaType = "raster" | "png";

export type BatchStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type StepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

/** Mirrors backend `ImageStatus` (models.py) — the record's audit lifecycle. */
export type ImageStatus =
  | "PENDING"
  | "AUDITING"
  | "PASSED"
  | "FLAGGED"
  | "APPROVED"
  | "READY";

/**
 * Record lifecycle state (backend wire values, uppercase, exactly one).
 *
 * COLLECTED = non-processed · APPROVED = pipeline passed · REJECTED = pipeline
 * failed · READY_TO_PUBLISH = manually queued for Adobe upload · PUBLISHED =
 * uploaded · AS_ACCEPTED = accepted by Adobe.
 */
export type ImageLifecycleState =
  | "COLLECTED"
  | "APPROVED"
  | "REJECTED"
  | "READY_TO_PUBLISH"
  | "PUBLISHED"
  | "AS_ACCEPTED";

export interface StepConfig {
  [key: string]: string | number | boolean | null;
}

export interface BatchStep {
  key: string;
  config: StepConfig;
}

export interface StepDefinition {
  key: string;
  label: string;
  description: string;
  media_types: MediaType[];
  default_config: StepConfig;
}

export interface StepCatalog {
  order: string[];
  steps: StepDefinition[];
  media_types: Record<MediaType, string[]>;
}

export interface StepProgress {
  status: StepStatus;
  message: string;
  counts: {
    succeeded?: number;
    failed?: number;
    skipped?: number;
    pending?: number;
  } | null;
}

export interface ImageRecord {
  id: string;
  filename: string;
  /** Absolute path of the source file on disk (backend-only concept, shown read-only). */
  original_path?: string;
  /** Absolute path of the current working file (cut-out after bg removal, etc.). */
  working_path?: string | null;
  thumbnail_path: string | null;
  status?: ImageStatus;
  stage: string;
  /** Lifecycle state; optional so pre-upgrade responses still type-check (see `stateFromLegacy`). */
  state?: ImageLifecycleState;
  /** Lifecycle flags — subset of the contract list; one of USED/UNUSED is always present. */
  flags?: string[];
  width: number | null;
  height: number | null;
  megapixels: number | null;
  file_size_bytes?: number;
  laplacian_variance?: number | null;
  ocr_text_detected?: boolean;
  ocr_text_content?: string | null;
  semantic_confidence_score?: number | null;
  semantic_flags?: string[] | null;
  generated_title: string | null;
  generated_description?: string | null;
  generated_keywords: string[] | null;
  /** Operator-chosen upload filename; null = derive from the title. */
  download_name?: string | null;
  /** Filename proposed by the metadata model (a proposal, not a decision). */
  suggested_filename?: string | null;
  /** The name actually uploaded — what the CSV Filename column carries. */
  upload_filename?: string | null;
  batch_id: string | null;
  /** Gallery folder this image lives in; null = ungrouped (top level). */
  group_id: string | null;
  /** Prompt Library link; null when the image has no known source prompt. */
  prompt_id?: string | null;
  is_used: boolean;
  used_at?: string | null;
  created_at: string;
  updated_at?: string;
  stage_updated_at: string | null;
  acceptance_score: number | null;
  acceptance_report?: Record<string, unknown> | null;
  stage_details?: Record<string, unknown> | null;
  refine_passes?: number;
  queued_stage?: string | null;
  category?: number | null;
}

export interface GalleryGroup {
  id: string;
  name: string;
  image_count: number;
  created_at: string;
}

export interface Batch {
  id: string;
  name: string;
  media_type: MediaType;
  steps: BatchStep[];
  profile_id: string | null;
  status: BatchStatus;
  /** When the batch entered the run queue (ISO); null unless queued/running. */
  queued_at: string | null;
  step_progress: Record<string, StepProgress> | null;
  error: string | null;
  record_count: number;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
}

export interface BatchDetail extends Batch {
  records: ImageRecord[];
}

export interface StepProfile {
  id: string;
  name: string;
  media_type: MediaType;
  steps: BatchStep[];
  created_at: string;
  updated_at: string;
}

export interface UploadResult {
  record_ids: string[];
  count: number;
  errors: string[];
}
