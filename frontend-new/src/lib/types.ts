/** Shared API types for the batch studio (mirrors backend/schemas.py). */

export type MediaType = "raster" | "png";

export type BatchStatus =
  | "draft"
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
  thumbnail_path: string | null;
  stage: string;
  width: number | null;
  height: number | null;
  megapixels: number | null;
  generated_title: string | null;
  generated_keywords: string[] | null;
  batch_id: string | null;
  /** Gallery folder this image lives in; null = ungrouped (top level). */
  group_id: string | null;
  is_used: boolean;
  created_at: string;
  stage_updated_at: string | null;
  acceptance_score: number | null;
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
