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
 * Full-viewport preview: fit-to-viewport on open, wheel zoom, direct drag
 * pan (no modifier), double-click for 100%, keyboard navigation and a direct
 * download.
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
  const stageRef = useRef<HTMLDivElement | null>(null);
  const { transform, cursor, startPan, movePan, endPan, zoomBy, fit, actual } =
    useViewerTransform(imageRef, stageRef, record !== null);

  useEffect(() => setMounted(true), []);

  // Fit whenever a different image is shown: a big image must never open at
  // 100% (task 05) — scale down until the whole frame is visible. Dimensions
  // come from the record so the fit is right before the <img> even loads;
  // onLoad re-fits as a fallback when the record carries no geometry.
  useEffect(() => {
    if (!record) return;
    setShowInfo(true);
    fit(record.width ?? undefined, record.height ?? undefined);
  }, [record, fit]);

  useEffect(() => {
    if (!record) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      else if (event.key === "ArrowLeft") onNavigate(-1);
      else if (event.key === "ArrowRight") onNavigate(1);
      else if (event.key === "+" || event.key === "=") zoomBy(1.25);
      else if (event.key === "-") zoomBy(1 / 1.25);
      else if (event.key === "0") fit();
      else if (event.key === "1") actual();
      else if (event.key.toLowerCase() === "h") setShowInfo((v) => !v);
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [record, onClose, onNavigate, zoomBy, fit, actual]);

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
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => zoomBy(1 / 1.25)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-parchment-500/50 bg-parchment-50/10 font-stamp text-ink-50 hover:bg-parchment-50/20"
            aria-label="Zoom out"
          >
            −
          </button>
          <span className="inline-flex h-8 w-14 items-center justify-center font-stamp text-[11px] text-ink-400">
            {Math.round(transform.scale * 100)}%
          </span>
          <button
            type="button"
            onClick={() => zoomBy(1.25)}
            className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-parchment-500/50 bg-parchment-50/10 font-stamp text-ink-50 hover:bg-parchment-50/20"
            aria-label="Zoom in"
          >
            +
          </button>
          <button
            type="button"
            onClick={() => fit()}
            className="inline-flex h-8 items-center justify-center rounded-sm border border-parchment-500/50 bg-parchment-50/10 px-2 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-parchment-50/20"
            title="Fit the whole image in the viewport (0)"
          >
            Fit
          </button>
          <button
            type="button"
            onClick={actual}
            className="inline-flex h-8 items-center justify-center rounded-sm border border-parchment-500/50 bg-parchment-50/10 px-2 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-parchment-50/20"
            title="Actual size: 1 monitor pixel per image pixel (1)"
          >
            100%
          </button>
          <a
            href={`${full}?download=1`}
            className="ml-1 inline-flex h-8 items-center justify-center rounded-sm border border-brass-400/60 bg-brass-300/20 px-3 font-stamp text-[11px] uppercase tracking-wider text-brass-300 hover:bg-brass-300/30"
          >
            ↓ Download
          </a>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-8 items-center justify-center rounded-sm border border-parchment-500/50 px-3 font-stamp text-[11px] uppercase tracking-wider text-ink-50 hover:bg-parchment-50/20"
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
        onDoubleClick={() => {
          // Double-click = 100% for pixel inspection; from 100% it returns
          // to fit so a second double-click is never a dead end.
          if (Math.abs(transform.scale - 1) < 0.01) fit();
          else actual();
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          ref={imageRef}
          src={full}
          alt={caption}
          draggable={false}
          onLoad={() => fit()}
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
          Wheel zoom · drag pan · double-click 100% · 0 fit · H hide HUD
        </p>
      </div>
    </div>,
    document.body
  );
}
