"use client";

import { FlaskConical } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/cn";

/**
 * Where the Prompt Research workspace lives.
 *
 * Exported so the header and any other entry point cannot disagree about the
 * destination — two hard-coded paths is how a link quietly starts pointing at a
 * route that was renamed.
 */
export const RESEARCH_HREF = "/research";

/**
 * The header entry to Prompt Research — **icon only**.
 *
 * Icon-only because the header already carries the stage rail, the published
 * gallery link, the upload table and the settings gear; a labelled button would
 * push the stage strip into wrapping at the widths this app is used at. The
 * `title` and `aria-label` carry the name, so the control is still identifiable
 * and screen-reader accessible without the visible text.
 */
export default function ResearchLink({ className }: { className?: string }) {
  const pathname = usePathname();
  const isActive = pathname.startsWith(RESEARCH_HREF);

  return (
    <Link
      href={RESEARCH_HREF}
      title="Prompt Research — research a niche and write prompts"
      aria-label="Prompt Research"
      aria-current={isActive ? "page" : undefined}
      className={cn(
        "inline-flex items-center justify-center rounded-lg p-1.5 transition-colors duration-150",
        isActive
          ? "bg-accent-500/15 text-accent-200"
          : "text-navy-300 hover:bg-navy-750/70 hover:text-navy-100",
        className
      )}
    >
      <FlaskConical className="h-3.5 w-3.5" aria-hidden />
    </Link>
  );
}
