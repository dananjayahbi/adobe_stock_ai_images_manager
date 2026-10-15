import Link from "next/link";

import type { PlatformMeta } from "@/lib/platforms";

/**
 * One platform in the master picker — the entire card is the link.
 *
 * Hierarchy is deliberate: the available platform wears the oxblood "Live"
 * stamp, a heavier display name and an enter affordance; coming-soon entries
 * stay muted with a plain outline chip. Status is carried by text, never by
 * color alone.
 */
export default function PlatformCard({ platform }: { platform: PlatformMeta }) {
  const live = platform.status === "available";

  return (
    <Link
      href={platform.route}
      aria-label={`${platform.name} — ${live ? "open the pipeline" : "coming soon"}`}
      className={`group relative flex h-full flex-col frame-card px-5 py-6 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 ${
        live
          ? "border-brass-400/70 hover:border-brass-400 hover:shadow-raised"
          : "hover:border-parchment-500 hover:bg-parchment-200/40"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        {live ? (
          <span className="stamp animate-stamp-in">Live</span>
        ) : (
          <span className="label-caps rounded-full border border-dashed border-parchment-500 px-2.5 py-1">
            Coming soon
          </span>
        )}
        <span
          aria-hidden="true"
          className={`font-stamp text-sm transition-transform group-hover:translate-x-1 ${
            live ? "text-oxblood-400" : "text-ink-400/60"
          }`}
        >
          →
        </span>
      </div>

      <h2
        className={`mt-4 font-display leading-tight ${
          live ? "text-2xl text-ink-800" : "text-xl text-ink-600"
        }`}
      >
        {platform.name}
      </h2>

      <p
        className={`mt-2 text-sm leading-relaxed ${
          live ? "text-ink-400" : "text-ink-400/70"
        }`}
      >
        {platform.tagline}
      </p>

      <span className={`label-caps mt-auto pt-5 ${live ? "text-oxblood-400" : ""}`}>
        {live ? "Enter the studio" : "In the works"}
      </span>
    </Link>
  );
}
