"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export interface Transform {
  scale: number;
  x: number;
  y: number;
}

const MIN_SCALE = 0.05;
const MAX_SCALE = 8;
/** Breathing room kept around an auto-fitted image (stage padding, px). */
const FIT_PADDING = 64;

/**
 * Zoom/pan state for the fullscreen viewer.
 *
 * - **Pan is direct**: dragging the stage always pans — no Space modifier.
 * - **Wheel zoom** attaches as a *non-passive* native listener keyed on
 *   `enabled`: React's `onWheel` is passive (preventDefault is ignored) and
 *   the stage does not exist until a record is open, so the effect must re-run
 *   when the viewer opens.
 * - **fit()** scales the image down until the whole frame is visible, capped
 *   at 100% — a small image is never upscaled past natural size.
 */
export function useViewerTransform(
  imageRef: React.RefObject<HTMLImageElement | null>,
  stageRef: React.RefObject<HTMLDivElement | null>,
  enabled: boolean
) {
  const [transform, setTransform] = useState<Transform>({ scale: 1, x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const drag = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(
    null
  );

  // Wheel zoom around the pointer. `enabled` flips exactly when a record
  // opens, which is when stageRef.current becomes non-null.
  useEffect(() => {
    if (!enabled) return;
    const stage = stageRef.current;
    if (!stage) return;
    const onWheel = (event: WheelEvent) => {
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
    };
    stage.addEventListener("wheel", onWheel, { passive: false });
    return () => stage.removeEventListener("wheel", onWheel);
  }, [enabled, imageRef, stageRef]);

  const startPan = useCallback(
    (event: React.PointerEvent) => {
      if (event.button !== 0) return;
      // HUD controls (Prev/Next, badges) live inside the stage — never steal
      // their press, and never start a pan from one.
      if ((event.target as HTMLElement).closest("button, a, input")) return;
      event.preventDefault();
      drag.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: transform.x,
        originY: transform.y,
      };
      setPanning(true);
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    },
    [transform]
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
    setPanning(false);
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

  /**
   * Scale the view so the *whole* image fits the stage, capped at 100%.
   * Dimensions may be passed explicitly (record.width/height) so the fit is
   * correct even before the <img> has loaded.
   */
  const fit = useCallback(
    (width?: number, height?: number) => {
      const image = imageRef.current;
      const stage = stageRef.current;
      const naturalWidth = width || image?.naturalWidth || 0;
      const naturalHeight = height || image?.naturalHeight || 0;
      if (!stage || !naturalWidth || !naturalHeight) return;
      const scale = Math.min(
        1,
        (stage.clientWidth - FIT_PADDING) / naturalWidth,
        (stage.clientHeight - FIT_PADDING) / naturalHeight
      );
      setTransform({ scale: clamp(scale, MIN_SCALE, 1), x: 0, y: 0 });
    },
    [imageRef, stageRef]
  );

  /** Exactly 100%: one monitor pixel per image pixel, centered. */
  const actual = useCallback(() => setTransform({ scale: 1, x: 0, y: 0 }), []);

  /** Back to 100% — kept for existing callers (Reset, the `0` key). */
  const reset = actual;

  const cursor = panning ? "grabbing" : "grab";

  return {
    transform,
    panning,
    cursor,
    startPan,
    movePan,
    endPan,
    zoomBy,
    fit,
    actual,
    reset,
    setTransform,
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
