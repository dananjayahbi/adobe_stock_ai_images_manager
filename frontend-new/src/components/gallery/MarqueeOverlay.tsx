"use client";

import type { MarqueeRect } from "@/hooks/useMarqueeSelect";

interface MarqueeOverlayProps {
  rect: MarqueeRect | null;
}

/**
 * The visible rubber band. Purely presentational — position/size are already
 * container-relative, so it just draws and never intercepts pointer events.
 */
export default function MarqueeOverlay({ rect }: MarqueeOverlayProps) {
  if (!rect) return null;
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute z-30 border-2 border-oxblood-400 bg-oxblood-400/10"
      style={{
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      }}
    />
  );
}
