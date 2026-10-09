"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface Transform {
  scale: number;
  x: number;
  y: number;
}

const MIN_SCALE = 0.2;
const MAX_SCALE = 8;

/**
 * Zoom/pan state for the fullscreen viewer.
 *
 * Spacebar-pan: while Space is held the cursor becomes a grab handle and
 * dragging pans even at 1× (where there is nothing to pan); releasing Space
 * restores normal behaviour. Wheel zooms around the pointer, so the pixel
 * under the cursor stays put.
 */
export function useViewerTransform(imageRef: React.RefObject<HTMLImageElement | null>) {
  const [transform, setTransform] = useState<Transform>({ scale: 1, x: 0, y: 0 });
  const [spaceHeld, setSpaceHeld] = useState(false);
  const drag = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(
    null
  );

  // Space is a modifier here — suppress page scroll while it is held.
  useEffect(() => {
    const isTyping = (target: EventTarget | null) =>
      target instanceof HTMLElement &&
      (target.tagName === "INPUT" || target.tagName === "TEXTAREA");
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code === "Space" && !isTyping(event.target)) {
        event.preventDefault();
        setSpaceHeld(true);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") setSpaceHeld(false);
    };
    const onBlur = () => setSpaceHeld(false);
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
    };
  }, []);

  const wheelZoom = useCallback((event: React.WheelEvent) => {
    event.preventDefault();
    const image = imageRef.current;
    if (!image) return;
    const rect = image.getBoundingClientRect();
    const offsetX = event.clientX - rect.left - rect.width / 2;
    const offsetY = event.clientY - rect.top - rect.height / 2;
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;

    setTransform((current) => {
      const nextScale = clamp(current.scale * factor, MIN_SCALE, MAX_SCALE);
      if (nextScale === current.scale) return current;
      // Keep the hovered point fixed: recompute the translation so the same
      // image-space point remains under the cursor after the zoom.
      const ratio = nextScale / current.scale;
      return {
        scale: nextScale,
        x: offsetX - ratio * (offsetX - current.x),
        y: offsetY - ratio * (offsetY - current.y),
      };
    });
  }, [imageRef]);

  const startPan = useCallback(
    (event: React.PointerEvent) => {
      if (!spaceHeld && transform.scale <= 1) return; // nothing to pan at 1×
      event.preventDefault();
      drag.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: transform.x,
        originY: transform.y,
      };
      (event.target as HTMLElement).setPointerCapture(event.pointerId);
    },
    [spaceHeld, transform]
  );

  const movePan = useCallback((event: React.PointerEvent) => {
    if (!drag.current) return;
    const { startX, startY, originX, originY } = drag.current;
    setTransform((current) => ({
      ...current,
      x: originX + (event.clientX - startX),
      y: originY + (event.clientY - startY),
    }));
  }, []);

  const endPan = useCallback(() => {
    drag.current = null;
  }, []);

  const zoomBy = useCallback(
    (factor: number) => {
      setTransform((current) => ({
        ...current,
        scale: clamp(current.scale * factor, MIN_SCALE, MAX_SCALE),
      }));
    },
    []
  );

  const reset = useCallback(() => setTransform({ scale: 1, x: 0, y: 0 }), []);

  const canPan = spaceHeld || transform.scale > 1;
  const cursor = canPan
    ? drag.current
      ? "grabbing"
      : "grab"
    : "zoom-in";

  return {
    transform,
    spaceHeld,
    canPan,
    cursor,
    wheelZoom,
    startPan,
    movePan,
    endPan,
    zoomBy,
    reset,
    setTransform,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
