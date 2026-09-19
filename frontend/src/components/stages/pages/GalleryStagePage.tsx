"use client";

import { Images } from "lucide-react";
import Link from "next/link";

import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";

/**
 * Stage 7 — Gallery.
 *
 * The terminal stage. Publishing copies each image to `ready_to_upload` and
 * embeds its metadata, after which the record is upload-ready. The link out to
 * the gallery browser is the only extra affordance the page needs.
 */
export default function GalleryStagePage() {
  return (
    <RunnableStagePage
      stageKey="gallery"
      emptyDescription="Push metadata-ready images here, then publish them to make them upload-ready."
      extraActions={() => (
        <Link
          href="/gallery"
          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-navy-700/60 bg-navy-800/50 px-3 text-xs font-medium text-navy-200 transition-colors duration-150 ease-swift hover:bg-navy-750 hover:text-navy-50"
        >
          <Images className="h-3.5 w-3.5" aria-hidden />
          Browse published
        </Link>
      )}
    />
  );
}
