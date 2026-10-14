"use client";

import { useEffect, useRef } from "react";

interface LoadSentinelProps {
  /** False when every page is loaded — the sentinel goes idle. */
  hasMore: boolean;
  onLoadMore: () => void;
  /** Distance from the viewport edge that triggers the next page. */
  rootMargin?: string;
}

/**
 * Invisible trigger placed after the grid: when it scrolls near the viewport,
 * the next page loads. IntersectionObserver means no scroll listeners and no
 * layout thrash — important once the gallery holds thousands of tiles.
 *
 * A manual button renders as a fallback for environments where the observer
 * never fires (and for keyboard users), so the last pages are always reachable.
 */
export default function LoadSentinel({
  hasMore,
  onLoadMore,
  rootMargin = "800px 0px",
}: LoadSentinelProps) {
  const ref = useRef<HTMLDivElement | null>(null);
  const callbackRef = useRef(onLoadMore);
  callbackRef.current = onLoadMore;

  useEffect(() => {
    const node = ref.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          callbackRef.current();
        }
      },
      { rootMargin }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, rootMargin]);

  if (!hasMore) return null;

  return (
    <div ref={ref} className="flex justify-center py-6">
      <button
        type="button"
        onClick={() => callbackRef.current()}
        className="rounded-sm border border-parchment-500 bg-parchment-50 px-4 py-2 font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-800"
      >
        Load more ↓
      </button>
    </div>
  );
}
