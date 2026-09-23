"use client";

import PublishedGalleryLink from "@/components/shell/PublishedGalleryLink";
import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";

/**
 * Stage 7 — Gallery.
 *
 * The terminal stage. Publishing copies each image to `ready_to_upload` and
 * embeds its metadata, after which the record is upload-ready. The link out to
 * the gallery browser is the only extra affordance the page needs.
 *
 * The link itself is shared with the header (`shell/PublishedGalleryLink`), so
 * the two can never point at different routes.
 */
export default function GalleryStagePage() {
  return (
    <RunnableStagePage
      stageKey="gallery"
      emptyDescription="Push metadata-ready images here, then publish them to make them upload-ready."
      extraActions={() => <PublishedGalleryLink variant="action" />}
    />
  );
}
