"use client";

/**
 * The Prompt Library's own route: the filters, the grid, and its empty states,
 * lifted off the `/adobe-stock/prompts` home page so the research workspace and
 * the library can each breathe.
 *
 * The header follows the app's standard pattern — label-caps eyebrow, display
 * title, then the reference's double rule — with a back link to the workspace.
 */
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import LibrarySection from "@/components/prompts/LibrarySection";
import { usePromptLibrary } from "@/hooks/usePromptLibrary";

export default function PromptLibraryPage() {
  const library = usePromptLibrary();

  return (
    <div className="space-y-8">
      {/* Header: back link, label + title, then the layered rule lines. */}
      <div>
        <Link
          href="/adobe-stock/prompts"
          className="inline-flex items-center gap-1.5 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400 transition-colors hover:text-oxblood-400"
        >
          <ArrowLeft className="h-3 w-3" aria-hidden />
          Back to Prompts
        </Link>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="label-caps">Saved prompts</p>
            <h1 className="mt-1 font-display text-3xl text-ink-800">
              Prompt library
            </h1>
          </div>
        </div>
        <div className="mt-3 h-px bg-brass-400/50" />
        <div className="mt-[2px] h-px bg-parchment-400" />
      </div>

      <LibrarySection library={library} />
    </div>
  );
}
