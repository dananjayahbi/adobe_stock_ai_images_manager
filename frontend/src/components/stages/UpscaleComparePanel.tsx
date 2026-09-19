"use client";

/**
 * Stage 3 comparison view for the inspection modal.
 *
 * Wraps `BeforeAfterCompare` with the Stage 3 specifics: which two URLs to
 * compare, and a caption describing exactly how the upscale was produced. The
 * caption matters because "4x model, 2 passes, TTA on" is the difference between
 * a plausible result and a suspicious one.
 */

import { Sparkles } from "lucide-react";

import { getPreviewUrl, type ImageRecord } from "@/lib/api";

import BeforeAfterCompare from "./BeforeAfterCompare";

interface UpscaleComparePanelProps {
  record: ImageRecord;
  /** Cache-buster so a re-run is not masked by the browser cache. */
  previewVersion?: string | number;
}

/** Stages at or after the upscale step, where an upscaled file can exist. */
const UPSCALED_OR_LATER = new Set([
  "UPSCALED",
  "REFINED",
  "COMPATIBLE",
  "INCOMPATIBLE",
  "METADATA_READY",
  "PUBLISHED",
]);

export default function UpscaleComparePanel({
  record,
  previewVersion,
}: UpscaleComparePanelProps) {
  const detail = record.stage_details?.upscale;

  // Before the upscale runs there is nothing to compare, and claiming otherwise
  // would be misleading.
  if (!UPSCALED_OR_LATER.has(record.stage) || !detail) {
    return (
      <p className="rounded-lg border border-dashed border-navy-800 px-4 py-6 text-center text-sm text-navy-400">
        No upscaled output yet. Run Stage 3 to create one.
      </p>
    );
  }

  const backend = typeof detail.backend === "string" ? detail.backend : undefined;
  const isNeural = backend === "upscayl";

  const captionParts: string[] = [];
  if (detail.model) {
    captionParts.push(
      `${detail.model}${detail.model_scale ? ` (${detail.model_scale}×)` : ""}`
    );
  }
  if (typeof detail.gpu_id === "number") captionParts.push(`GPU ${detail.gpu_id}`);
  if (typeof detail.passes === "number" && detail.passes > 1) {
    captionParts.push(`${detail.passes} passes`);
  }
  if (detail.tta) captionParts.push("TTA");
  if (typeof detail.target_long_edge === "number") {
    captionParts.push(`target ${detail.target_long_edge} px`);
  }
  if (backend) captionParts.push(backend);
  if (detail.srgb_embedded) captionParts.push("sRGB profile embedded");

  const warnings = Array.isArray(detail.warnings) ? detail.warnings : [];

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-lg border border-navy-800 bg-navy-950/50 px-3 py-2">
        <Sparkles
          className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${
            isNeural ? "text-fuchsia-400" : "text-amber-400"
          }`}
        />
        <div className="min-w-0 text-xs">
          <p className="text-navy-200">
            {isNeural
              ? "Neural upscale"
              : "Resampled only - the upscayl binary was not used"}
          </p>
          {captionParts.length > 0 && (
            <p className="mt-0.5 text-navy-400">{captionParts.join(" · ")}</p>
          )}
        </div>
      </div>

      {!isNeural && (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          This image was enlarged by interpolation, not by a neural network, so it
          gained no real detail. Check that the Upscayl binary is reachable before
          publishing.
        </p>
      )}

      {warnings.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}

      <BeforeAfterCompare
        beforeUrl={getPreviewUrl(record.id, "original", previewVersion)}
        afterUrl={getPreviewUrl(record.id, "upscaled", previewVersion)}
        beforeLabel="Original"
        afterLabel="Upscaled"
        beforeDimensions={
          detail.source_dimensions ??
          (record.width && record.height ? [record.width, record.height] : null)
        }
        afterDimensions={detail.output_dimensions ?? null}
      />
    </div>
  );
}
