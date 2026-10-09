"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { API_BASE_URL, thumbnailUrl } from "@/lib/client";
import { useViewerTransform } from "@/hooks/useViewerTransform";
import Badge from "@/components/ui/Badge";
import type { ImageRecord } from "@/lib/types";

interface ViewerModalProps {
  record: ImageRecord | null;
  onClose: () => void;
  onNavigate: (direction: -1 | 1) => void;
}

/**
 * Full-viewport preview: zoom (wheel / buttons / double-click), pan (drag,
 * or Space+drag at 1×), keyboard navigation, and a direct download.
 *
 * Portalled to `document.body` for the same reason as `Modal`: an ancestor
 * with `backdrop-filter` would otherwise clamp `position: fixed`.
 * Rendered separately from `Modal` because it takes the *entire* viewport
 * with no card chrome — a viewer is a different species from a dialog.
 */
export default function ViewerModal({ record, onClose, onNavigate }: ViewerModalProps) {
  const [mounted, setMounted] = useState(false);
  const [showInfo, setShowInfo] = useState(true);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const {
    transform,
    spaceHeld,
    canPan,
    cursor,
    startPan,
    movePan,
    endPan,
    zoomBy,
    reset,
    setTransform,
  } = useViewerTransform(imageRef);

  useEffect(() => setMounted(true), []);

  // Wheel must be a *non-passive* native listener: React registers onWheel
  // passively, so preventDefault would be ignored and the page behind would
  // scroll while zooming.
  const stageRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
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
        const nextScale = Math.min(8, Math.max(0.2, current.scale * factor));
        if (nextScale === current.scale) return current;
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
  }, [imageRef, setTransform]);

  // Reset the view whenever a different image is shown.
  useEffect(() => {
    reset();
    setShowInfo(true);
  }, [record?.id, reset]);

  useEffect(() => {
    if (!record) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowLeft") onNavigate(-1);
      else if (event.key === "ArrowRight") onNavigate(1);
      else if (event.key === "+" || event.key === "=") zoomBy(1.25);
      else if (event.key === "-") zoomBy(1 / 1.25);
      else if (event.key === "0") reset();
      else if (event.key.toLowerCase() === "h") setShowInfo((v) => !v);
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [record, onClose, onNavigate, zoomBy, reset]);

  if (!mounted || !record) return null;

  const thumb = thumbnailUrl(record.thumbnail_path);
  // Full-size source: the current working file (a cut-out after bg removal),
  // falling back to the thumbnail only if the record has no file yet.
  const full = `${API_BASE_URL}/api/records/${record.id}/file`;
  const caption =
    record.generated_title ||
    record.filename.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ");

  return createPortal(
    <div
      className="fixed inset-0 z-[120] flex flex-col bg-ink-900/95"
      role="dialog"
      aria-modal="true"
      aria-label={`Preview: ${caption}`}
    >
      {/* Top chrome */}
      <header className="flex items-center justify-between gap-4 border-b border-parchment-500/30 bg-ink-900/80 px-4 py-2.5">
        <div className="min-w-0">
          <p className="truncate font-display text-sm text-ink-50" title={caption}>
            {caption}
          </p>
          <p className="font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400">
            {record.stage.replace(/_/g, " ")}
            {spaceHeld && " · space pan"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => zoomBy(1 / 1.25)}
            className="h-8 w-8 rounded-sm border border-parchment-500/50 bg-parchment-50/10 font-stamp text-ink-50 hover:bg-parchment-50/20"
            aria-label="Zoom out"
          >
            −
          </button>
          <span className="w-14 text-center font-stamp text-[11px] text-ink-400">
            {Math.round(transform.scale * 100)}%
          </span>
          <button
            type="button"
            onClick={() => zoomBy(1.25)}
            className="h-8 w-8 rounded-sm border border-parchment-500/50 bg-parchment-50/10 font-stamp text-ink-50 hover:bg-parchment-50/20"
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            type="button"
            onClick={reset}
            className="h-8 rounded-sm border border-parchment-500/50 bg-parchment-50/10 px-2 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-parchment-50/20"
          >
            Reset
          </button>
          <a
            href={`${full}?download=1`}
            className="ml-1 h-8 rounded-sm border border-brass-400/60 bg-brass-300/20 px-3 font-stamp text-[11px] uppercase tracking-wider text-brass-300 hover:bg-brass-300/30"
          >
            ↓ Download
          </a>
          <button
            type="button"
            onClick={onClose}
            className="ml-1 h-8 rounded-sm border border-parchment-500/50 px-3 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-parchment-50/20"
            aria-label="Close preview"
          >
            ✕ Esc
          </button>
        </div>
      </header>

      {/* Stage */}
      <div
        ref={stageRef}
        className="relative flex-1 overflow-hidden"
        onPointerDown={startPan}
        onPointerMove={movePan}
        onPointerUp={endPan}
        onPointerCancel={endPan}
        onDoubleClick={() => (transform.scale > 1 ? reset() : zoomBy(2))}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imageRef}
          src={full}
          alt={caption}
          draggable={false}
          onError={(event) => {
            // No full-size file yet — fall back to the thumbnail.
            if (thumb && event.currentTarget.src !== thumb) event.currentTarget.src = thumb;
          }}
          className="absolute left-1/2 top-1/2 max-w-none select-none"
          style={{
            transform: `translate(-50%, -50%) translate(${transform.x}px, ${transform.y}px) scale(${transform.scale})`,
            cursor,
            imageRendering: transform.scale > 1.5 ? "pixelated" : "auto",
          }}
        />

        {showInfo && (
          <div className="absolute bottom-4 left-4 flex flex-wrap gap-2">
            <Badge tone="info">{record.stage.replace(/_/g, " ")}</Badge>
            {record.megapixels != null && <Badge>{record.megapixels.toFixed(1)} MP</Badge>}
            {record.acceptance_score != null && (
              <Badge tone={record.acceptance_score >= 0.8 ? "success" : "warn"}>
                {(record.acceptance_score * 100).toFixed(0)}%
              </Badge>
            )}
            <Badge>{Math.round(transform.scale * 100)}%</Badge>
          </div>
        )}

        <div className="absolute bottom-4 right-4 flex gap-2">
          <button
            type="button"
            onClick={() => onNavigate(-1)}
            className="h-9 rounded-sm border border-parchment-500/50 bg-ink-900/70 px-3 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-ink-900"
          >
            ← Prev
          </button>
          <button
            type="button"
            onClick={() => onNavigate(1)}
            className="h-9 rounded-sm border border-parchment-500/50 bg-ink-900/70 px-3 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-ink-900"
          >
            Next →
          </button>
        </div>

        <p className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400/70">
          Wheel zoom · double-click fit · Space+drag pan · H hide HUD
        </p>
      </div>
    </div>,
    document.body
  );
}
