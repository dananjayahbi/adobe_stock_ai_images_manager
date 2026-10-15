import Link from "next/link";

import type { PlatformMeta } from "@/lib/platforms";

/**
 * Placeholder for a platform whose integration hasn't landed yet.
 *
 * Server-renderable (no hooks) so route pages keep plain metadata + static
 * composition; visuals mirror the home hero — frame card, script flourish,
 * stamp chip — so a "not ready" route still feels engraved.
 */
export default function PlatformComingSoon({
  platform,
}: {
  platform: PlatformMeta;
}) {
  return (
    <div className="mx-auto max-w-2xl space-y-6 py-6 sm:py-10">
      <section className="relative overflow-hidden frame-card px-6 py-12 text-center sm:py-16">
        {/* Status chip, like a stamped inspection mark. */}
        <p className="stamp animate-stamp-in">Coming soon</p>

        <h1 className="mt-5 font-display text-4xl leading-tight text-ink-800 sm:text-5xl">
          {platform.name}
        </h1>

        <p className="mt-3 font-script text-2xl text-oxblood-400">
          {platform.tagline}
        </p>

        <div className="divider-dashed mx-auto mt-7 max-w-md" />

        <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-ink-400 sm:text-lg">
          This workspace is under construction. The shared processing steps —
          upscale, QC, metadata — will be configured here once the integration
          lands.
        </p>

        <div className="mt-8">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 rounded-sm border border-parchment-500 bg-parchment-50 px-6 py-3 font-stamp text-xs uppercase tracking-[0.14em] text-ink-800 transition-all hover:border-parchment-600 hover:bg-parchment-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400"
          >
            ← All platforms
          </Link>
        </div>

        {/* Corner flourishes, matching the home hero's certificate corners. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-3 right-3 font-script text-3xl text-brass-400/50"
        >
          ✦
        </span>
      </section>
    </div>
  );
}
