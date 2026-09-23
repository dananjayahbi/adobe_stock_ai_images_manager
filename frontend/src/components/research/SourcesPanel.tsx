"use client";

import { ExternalLink, Globe } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ResearchSource } from "@/lib/research";

export interface SourcesPanelProps {
  sources: ResearchSource[];
  className?: string;
}

/** Trim a URL to its host and path, so a long link stays readable. */
function shortUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const path = parsed.pathname === "/" ? "" : parsed.pathname;
    return `${parsed.host}${path}`.slice(0, 72);
  } catch {
    return url.slice(0, 72);
  }
}

/**
 * Every site the agent actually read.
 *
 * The operator asked to see "the exploring sites the research agents do", and
 * this is the durable half of that: the live step list scrolls away, but the
 * sources stay so a claim in the answer can be checked against what was read.
 *
 * Links are rendered as plain anchors with `rel="noreferrer noopener"` — the URL
 * came from a third-party search result, so it is untrusted text.
 */
export default function SourcesPanel({ sources, className }: SourcesPanelProps) {
  if (sources.length === 0) return null;

  return (
    <section className={cn("space-y-2", className)}>
      <header className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-navy-400">
        <Globe className="h-3.5 w-3.5" aria-hidden />
        Sources read
        <span className="rounded-full bg-navy-750/70 px-2 py-0.5 tabular-nums text-navy-300">
          {sources.length}
        </span>
      </header>

      <ul className="space-y-1.5">
        {sources.map((source) => (
          <li key={source.url}>
            <a
              href={source.url}
              target="_blank"
              rel="noreferrer noopener"
              className="group block rounded-lg border border-navy-700/40 bg-navy-850/40 px-2.5 py-2 transition-colors hover:border-accent-500/40 hover:bg-navy-800/60"
            >
              <div className="flex items-start gap-2">
                <ExternalLink
                  className="mt-0.5 h-3 w-3 shrink-0 text-navy-500 transition-colors group-hover:text-accent-300"
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className="line-clamp-2 text-xs font-medium text-navy-200 group-hover:text-navy-50">
                    {source.title || shortUrl(source.url)}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-navy-500">
                    {source.display_url || shortUrl(source.url)}
                  </p>
                </div>
              </div>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
