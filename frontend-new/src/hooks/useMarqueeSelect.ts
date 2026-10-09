"use client";

import { useCallback, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

export interface MarqueeRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

interface MarqueeOptions {
  /** Rubber-band selection only runs while the gallery is in select mode. */
  enabled: boolean;
  containerRef: React.RefObject<HTMLElement | null>;
  /** Called with the ids of every `[data-record-id]` tile the box touches. */
  onSelect: (recordIds: string[], additive: boolean) => void;
}

const DRAG_THRESHOLD_PX = 5;
/**
 * The click a drag leaves behind fires in the same event loop turn as
 * pointerup — a 300 ms window reliably covers it while never eating a
 * deliberate click made noticeably later.
 */
const CLICK_SUPPRESS_MS = 300;

/**
 * Windows-desktop style rubber-band selection over the gallery grid.
 *
 * A press starts *tracking*, not selecting: only after the pointer moves past
 * the threshold does the marquee engage (and the pointer capture latch, so
 * the drag survives leaving the container). A press without movement is a
 * plain click and reaches the tile untouched — which is why a click still
 * toggles selection while a drag paints a box.
 *
 * The click that follows a completed drag is swallowed once via a capture
 * handler: without it, releasing the drag *on* a tile would toggle it right
 * after the marquee already selected it.
 */
export function useMarqueeSelect({ enabled, containerRef, onSelect }: MarqueeOptions) {
  const [rect, setRect] = useState<MarqueeRect | null>(null);
  const start = useRef<{ x: number; y: number } | null>(null);
  const dragging = useRef(false);
  const suppressClick = useRef(false);

  const onPointerDown = useCallback(
    (event: ReactPointerEvent) => {
      if (!enabled || event.button !== 0) return;
      start.current = { x: event.clientX, y: event.clientY };
      dragging.current = false;
    },
    [enabled]
  );

  const onPointerMove = useCallback(
    (event: ReactPointerEvent) => {
      if (!start.current) return;
      const dx = event.clientX - start.current.x;
      const dy = event.clientY - start.current.y;
      if (!dragging.current) {
        if (Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
        dragging.current = true;
        // Latch only once the drag is real — capturing on plain presses would
        // retarget the click away from the tile and break click-to-toggle.
        containerRef.current?.setPointerCapture(event.pointerId);
      }
      const container = containerRef.current;
      if (!container) return;
      event.preventDefault(); // no text selection / native image drag
      const bounds = container.getBoundingClientRect();
      const left = Math.min(event.clientX, start.current.x) - bounds.left;
      const top = Math.min(event.clientY, start.current.y) - bounds.top;
      setRect({
        left,
        top,
        width: Math.abs(dx),
        height: Math.abs(dy),
      });
    },
    [containerRef]
  );

  const onPointerUp = useCallback(
    (event: ReactPointerEvent) => {
      if (!start.current) return;
      const wasDrag = dragging.current;
      const from = start.current;
      start.current = null;
      dragging.current = false;
      setRect(null);
      if (!wasDrag) return; // plain click — let it through

      const container = containerRef.current;
      if (!container) return;
      const box = {
        left: Math.min(from.x, event.clientX),
        right: Math.max(from.x, event.clientX),
        top: Math.min(from.y, event.clientY),
        bottom: Math.max(from.y, event.clientY),
      };

      const ids: string[] = [];
      container.querySelectorAll<HTMLElement>("[data-record-id]").forEach((el) => {
        const r = el.getBoundingClientRect();
        const intersects =
          r.right >= box.left && r.left <= box.right && r.bottom >= box.top && r.top <= box.bottom;
        if (intersects && el.dataset.recordId) ids.push(el.dataset.recordId);
      });

      suppressClick.current = true;
      window.setTimeout(() => {
        suppressClick.current = false;
      }, CLICK_SUPPRESS_MS);
      onSelect(ids, event.ctrlKey || event.metaKey);
    },
    [containerRef, onSelect]
  );

  /** Swallow the click a completed drag leaves behind (capture phase). */
  const onClickCapture = useCallback((event: React.MouseEvent) => {
    if (!suppressClick.current) return;
    suppressClick.current = false;
    event.stopPropagation();
    event.preventDefault();
  }, []);

  return { rect, onPointerDown, onPointerMove, onPointerUp, onClickCapture };
}
