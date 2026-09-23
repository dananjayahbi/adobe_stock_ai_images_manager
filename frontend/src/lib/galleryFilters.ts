import type { PipelineStage } from "@/lib/stages";

/**
 * The gallery's filter vocabulary, in one place.
 *
 * Kept out of the components so the toolbar, the search bar and the data hook
 * all read the same definitions. Three places each declaring "what the filters
 * are" is how a chip ends up rendered with no matching query parameter — a
 * control that looks live and does nothing.
 */

/** Which slice of the pipeline the gallery shows. */
export type GalleryScope = "published" | "all";

export interface GalleryScopeSpec {
  key: GalleryScope;
  label: string;
  hint: string;
}

/**
 * Scopes are defined by **stage**, not by the legacy `status` column.
 *
 * "Published" used to be expressed as `status=READY`, which is a different
 * question: `status` is the QC verdict and `stage` is the pipeline position. A
 * record can be READY while sitting at METADATA_READY (it was approved but not
 * yet published), so the old filter included assets the operator had not
 * finished. Asking by stage is what "browse published" actually means.
 */
export const GALLERY_SCOPES: GalleryScopeSpec[] = [
  {
    key: "published",
    label: "Published",
    hint: "Finished assets, staged in ready_to_upload",
  },
  {
    key: "all",
    label: "All stages",
    hint: "Every record, whatever stage it reached",
  },
];

/** Stages that count as "published" for the gallery's default scope. */
export const PUBLISHED_STAGES: PipelineStage[] = ["PUBLISHED"];

/** Usage axis - independent of the stage scope, and combined with it. */
export type GalleryUsageFilter = "all" | "unused" | "used";

export interface GalleryUsageSpec {
  key: GalleryUsageFilter;
  label: string;
}

export const GALLERY_USAGE_FILTERS: GalleryUsageSpec[] = [
  { key: "unused", label: "Unused" },
  { key: "used", label: "Used" },
  { key: "all", label: "All" },
];

/**
 * Empty-state copy, keyed by what the operator can actually change.
 *
 * A single generic "no images" message is unhelpful when the cause is a search
 * term the operator forgot about — they would conclude the gallery was empty.
 */
export function galleryEmptyMessage(options: {
  hasSearch: boolean;
  usageFilter: GalleryUsageFilter;
  scope: GalleryScope;
}): { title: string; description: string } {
  const { hasSearch, usageFilter, scope } = options;

  if (hasSearch) {
    return {
      title: "No images match your search",
      description:
        "Try a different word, or clear the search to see everything in this scope.",
    };
  }

  if (usageFilter === "unused") {
    return {
      title: "Nothing unused here",
      description:
        scope === "published"
          ? "Every published asset has been marked as used. Switch to All to see them."
          : "Every asset has been marked as used. Switch to All to see them.",
    };
  }

  if (usageFilter === "used") {
    return {
      title: "Nothing marked as used yet",
      description:
        "Assets you mark as used while uploading will be collected here.",
    };
  }

  return {
    title: "No published images yet",
    description:
      "Publish metadata-ready images from Stage 7, then they will appear here ready to upload.",
  };
}
