"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { ALL_STAGE_META } from "@/lib/stageMeta";
import { fetchQueueSummary, type QueueSummary } from "@/lib/api";

/**
 * Horizontal stage strip used in the header.
 *
 * Each stage is a real route. The connector line between steps makes the
 * pipeline order legible at a glance, and a pending-queue badge on the *next*
 * stage is what tells the operator there is work waiting after a push.
 */
export default function StageProgressRail() {
  const pathname = usePathname();
  const [summary, setSummary] = useState<QueueSummary | null>(null);

  // Poll the queue depth so a push from another page shows up here.
  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await fetchQueueSummary();
        if (!cancelled) setSummary(data);
      } catch {
        // The badge is a convenience; a failure must not break navigation.
      }
    }

    void load();
    const timer = setInterval(load, 8000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <nav
      aria-label="Pipeline stages"
      className="flex min-w-0 items-center overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {ALL_STAGE_META.map((meta, index) => {
        const Icon = meta.icon;
        const href = `/stages/${meta.slug}`;
        const isActive = pathname.startsWith(href);
        const pending = summary?.counts?.[meta.slug] ?? 0;
        const isLast = index === ALL_STAGE_META.length - 1;

        return (
          <div key={meta.slug} className="flex shrink-0 items-center">
            <Link
              href={href}
              aria-current={isActive ? "page" : undefined}
              title={`Stage ${meta.number} · ${meta.name}`}
              className={cn(
                "group relative flex shrink-0 items-center gap-2 rounded-lg px-2 py-1.5 2xl:px-2.5",
                "transition-colors duration-150 ease-swift",
                isActive
                  ? "bg-accent-500/15 text-accent-100"
                  : "text-navy-300 hover:bg-navy-800/70 hover:text-navy-100"
              )}
            >
              <span
                className={cn(
                  "grid h-5 w-5 shrink-0 place-items-center rounded-md text-[10px] font-bold tabular-nums",
                  isActive
                    ? "bg-accent-500 text-navy-950"
                    : "bg-navy-750 text-navy-300 group-hover:bg-navy-700"
                )}
              >
                {meta.number}
              </span>
              <Icon
                className={cn(
                  "hidden h-4 w-4 shrink-0 2xl:block",
                  isActive ? "text-accent-300" : "text-navy-400"
                )}
                aria-hidden
              />
              <span className="hidden whitespace-nowrap text-xs font-medium xl:block">
                {meta.name}
              </span>
              {pending > 0 ? (
                <span
                  title={`${pending} waiting in this stage's queue`}
                  className="ml-0.5 grid h-4 min-w-4 shrink-0 place-items-center rounded-full bg-accent-500/25 px-1 text-[10px] font-bold tabular-nums text-accent-200"
                >
                  {pending > 99 ? "99+" : pending}
                </span>
              ) : null}
            </Link>
            {!isLast ? (
              <span
                aria-hidden
                className={cn(
                  "mx-0.5 h-px w-3 shrink-0 xl:w-4 2xl:w-5",
                  isActive ? "bg-accent-500/50" : "bg-navy-700/70"
                )}
              />
            ) : null}
          </div>
        );
      })}
    </nav>
  );
}
