"use client";

import { Images } from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/cn";

/**
 * Where the published gallery lives.
 *
 * Exported so the header and the Stage 7 page cannot disagree about the
 * destination — two hard-coded paths is how a link quietly starts pointing at a
 * route that was renamed.
 */
export const PUBLISHED_GALLERY_HREF = "/gallery";

export interface PublishedGalleryLinkProps {
  /** `header` is the compact nav pill; `action` matches a stage-page button. */
  variant?: "header" | "action";
  className?: string;
}

/**
 * The link to the **published gallery** — the endpoint of the whole system.
 *
 * It was previously reachable only from Stage 7's page, which meant an operator
 * on any other stage had to navigate to Stage 7 first to reach the assets they
 * had already finished. The published gallery is the one place worth reaching
 * from anywhere, so it now lives in the header as well.
 *
 * One component with two skins rather than two links: the destination, the icon
 * and the label are defined once.
 */
export default function PublishedGalleryLink({
  variant = "header",
  className,
}: PublishedGalleryLinkProps) {
  const isHeader = variant === "header";

  return (
    <Link
      href={PUBLISHED_GALLERY_HREF}
      title="Browse the published gallery — upload-ready assets"
      className={cn(
        isHeader
          ? "hidden items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150 sm:inline-flex text-navy-300 hover:bg-navy-750/70 hover:text-navy-100"
          : "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-navy-700/60 bg-navy-800/50 px-3 text-xs font-medium text-navy-200 transition-colors duration-150 ease-swift hover:bg-navy-750 hover:text-navy-50",
        className
      )}
    >
      <Images className="h-3.5 w-3.5" aria-hidden />
      Browse published
    </Link>
  );
}
