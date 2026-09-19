"use client";

/**
 * Before/after comparison for the Stage 3 upscale output.
 *
 * Judging an upscale means looking at the *same* region of both images, so a
 * naive side-by-side is close to useless: the two panes drift apart as soon as
 * you zoom. This component keeps a single shared viewport transform, so panning
 * or zooming one pane moves the other to the matching pixel.
 *
 * A draggable split view is also offered, which is the fastest way to see
 * whether edges gained real detail or were merely sharpened.
 */

import { Columns2, Loader2, Maximize2, SplitSquareHorizontal, ZoomIn, ZoomOut } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

type CompareMode = "split" | "side";

interface BeforeAfterCompareProps {
  beforeUrl: string;
  afterUrl: string;
  beforeLabel?: string;
  afterLabel?: string;
  /** Short summary of what produced the "after" image. */
  caption?: string;
  beforeDimensions?: [number, number] | null;
  afterDimensions?: [number, number] | null;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 8;

export default function BeforeAfterCompare({
  beforeUrl,
  afterUrl,
  beforeLabel = "Before",
  afterLabel = "After",
  caption,
  beforeDimensions,
  afterDimensions,
}: BeforeAfterCompareProps) {
  const [mode, setMode] = useState<CompareMode>("split");
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [split, setSplit] = useState(50);
  const [loaded, setLoaded] = useState({ before: false, after: false });

  const splitRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);
  const draggingSplit = useRef(false);

  // Reset the viewport when either image changes so a previous zoom level does
  // not silently apply to a different pair.
  useEffect(() => {
    setZoom(1);
    setOffset({ x: 0, y: 0 });
    setLoaded({ before: false, after: false });
  }, [beforeUrl, afterUrl]);

  const clampOffset = useCallback(
    (next: { x: number; y: number }, scale: number) => {
      // Keep the image covering the frame: at 2x zoom the pan range is the
      // extra 100% of the frame, so the offset may not exceed that.
      const limit = ((scale - 1) / 2) * 100;
      return {
        x: Math.max(-limit, Math.min(limit, next.x)),
        y: Math.max(-limit, Math.min(limit, next.y)),
      };
    },
    []
  );

  const applyZoom = useCallback(
    (next: number) => {
      const scale = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, next));
      setZoom(scale);
      setOffset((current) => clampOffset(current, scale));
    },
    [clampOffset]
  );

  // Wheel zoom, anchored on the pointer so zooming follows the cursor.
  const handleWheel = useCallback(
    (event: React.WheelEvent) => {
      event.preventDefault();
      const rect = event.currentTarget.getBoundingClientRect();
      const ratio = 1 + (event.deltaY < 0 ? 0.2 : -0.2);
      const next = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * ratio));
      if (next === zoom) return;

      // Move the offset so the point under the cursor stays put.
      const px = (event.clientX - rect.left) / rect.width - 0.5;
      const py = (event.clientY - rect.top) / rect.height - 0.5;
      const factor = next / zoom;
      setZoom(next);
      setOffset((current) =>
        clampOffset(
          {
            x: current.x * factor - px * 100 * (factor - 1),
            y: current.y * factor - py * 100 * (factor - 1),
          },
          next
        )
      );
    },
    [clampOffset, zoom]
  );

  const handleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      if (zoom <= 1) return;
      event.preventDefault();
      dragState.current = {
        x: event.clientX,
        y: event.clientY,
        ox: offset.x,
        oy: offset.y,
      };
    },
    [offset.x, offset.y, zoom]
  );

  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (draggingSplit.current && splitRef.current) {
        const rect = splitRef.current.getBoundingClientRect();
        const percent = ((event.clientX - rect.left) / rect.width) * 100;
        setSplit(Math.max(2, Math.min(98, percent)));
        return;
      }

      const drag = dragState.current;
      if (!drag) return;
      const rect = (event.target as HTMLElement)?.closest("[data-compare-frame]");
      const width = rect?.clientWidth ?? 1;
      const height = rect?.clientHeight ?? 1;
      setOffset(
        clampOffset(
          {
            x: drag.ox + ((event.clientX - drag.x) / width) * 100,
            y: drag.oy + ((event.clientY - drag.y) / height) * 100,
          },
          zoom
        )
      );
    };

    const onUp = () => {
      dragState.current = null;
      draggingSplit.current = false;
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [clampOffset, zoom]);

  const transform = `translate(${offset.x}%, ${offset.y}%) scale(${zoom})`;
  const imageClass = "h-full w-full object-contain transition-transform duration-75";

  const frameProps = {
    "data-compare-frame": true,
    onWheel: handleWheel,
    onMouseDown: handleMouseDown,
    style: { cursor: zoom > 1 ? "grab" : "default" } as React.CSSProperties,
  };

  return (
    <section className="space-y-2">
      <header className="flex flex-wrap items-center gap-2">
        <div className="flex overflow-hidden rounded-md border border-navy-700">
          <button
            type="button"
            onClick={() => setMode("split")}
            aria-pressed={mode === "split"}
            className={`inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium transition-colors ${
              mode === "split"
                ? "bg-accent-500/20 text-accent-200"
                : "bg-navy-800/60 text-navy-300 hover:bg-navy-700"
            }`}
          >
            <SplitSquareHorizontal className="h-3.5 w-3.5" />
            Split
          </button>
          <button
            type="button"
            onClick={() => setMode("side")}
            aria-pressed={mode === "side"}
            className={`inline-flex items-center gap-1 border-l border-navy-700 px-2.5 py-1 text-xs font-medium transition-colors ${
              mode === "side"
                ? "bg-accent-500/20 text-accent-200"
                : "bg-navy-800/60 text-navy-300 hover:bg-navy-700"
            }`}
          >
            <Columns2 className="h-3.5 w-3.5" />
            Side by side
          </button>
        </div>

        <div className="flex items-center gap-1 rounded-md border border-navy-700 bg-navy-800/60">
          <button
            type="button"
            onClick={() => applyZoom(zoom / 1.5)}
            disabled={zoom <= MIN_ZOOM}
            aria-label="Zoom out"
            className="p-1.5 text-navy-300 transition-colors hover:text-navy-50 disabled:opacity-40"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <span className="w-12 text-center text-xs tabular-nums text-navy-300">
            {zoom.toFixed(1)}×
          </span>
          <button
            type="button"
            onClick={() => applyZoom(zoom * 1.5)}
            disabled={zoom >= MAX_ZOOM}
            aria-label="Zoom in"
            className="p-1.5 text-navy-300 transition-colors hover:text-navy-50 disabled:opacity-40"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={() => applyZoom(1)}
            aria-label="Reset zoom"
            className="border-l border-navy-700 p-1.5 text-navy-300 transition-colors hover:text-navy-50"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        </div>

        <span className="text-xs text-navy-400">
          Scroll to zoom, drag to pan. Both views stay locked together.
        </span>
      </header>

      {mode === "split" ? (
        <div
          ref={splitRef}
          {...frameProps}
          className="relative h-[28rem] select-none overflow-hidden rounded-lg border border-navy-800 bg-navy-950"
        >
          {/* After, as the base layer. */}
          <img
            src={afterUrl}
            alt={afterLabel}
            draggable={false}
            onLoad={() => setLoaded((s) => ({ ...s, after: true }))}
            className={imageClass}
            style={{ transform }}
          />
          {/* Before, clipped to the left of the divider. */}
          <div
            className="absolute inset-0 overflow-hidden"
            style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          >
            <img
              src={beforeUrl}
              alt={beforeLabel}
              draggable={false}
              onLoad={() => setLoaded((s) => ({ ...s, before: true }))}
              className={imageClass}
              style={{ transform }}
            />
          </div>

          {/* Divider. */}
          <div
            className="absolute inset-y-0 w-0.5 cursor-col-resize bg-accent-400/90"
            style={{ left: `${split}%` }}
            onMouseDown={(event) => {
              event.preventDefault();
              draggingSplit.current = true;
            }}
            role="separator"
            aria-label="Comparison divider"
            aria-valuenow={Math.round(split)}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <span className="absolute left-1/2 top-1/2 h-7 w-7 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent-400 bg-navy-900" />
          </div>

          <Tag position="left">{beforeLabel}</Tag>
          <Tag position="right">{afterLabel}</Tag>

          {!(loaded.before && loaded.after) && <Spinner />}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {[
            { url: beforeUrl, label: beforeLabel, dims: beforeDimensions, key: "before" },
            { url: afterUrl, label: afterLabel, dims: afterDimensions, key: "after" },
          ].map((pane) => (
            <figure key={pane.key} className="space-y-1.5">
              <div
                {...frameProps}
                className="relative h-[24rem] select-none overflow-hidden rounded-lg border border-navy-800 bg-navy-950"
              >
                <img
                  src={pane.url}
                  alt={pane.label}
                  draggable={false}
                  onLoad={() =>
                    setLoaded((s) => ({ ...s, [pane.key]: true } as typeof s))
                  }
                  className={imageClass}
                  style={{ transform }}
                />
                <Tag position="left">{pane.label}</Tag>
                {!loaded[pane.key as "before" | "after"] && <Spinner />}
              </div>
              {pane.dims && (
                <figcaption className="text-center text-xs tabular-nums text-navy-400">
                  {pane.dims[0]}×{pane.dims[1]}
                </figcaption>
              )}
            </figure>
          ))}
        </div>
      )}

      {caption && <p className="text-xs text-navy-400">{caption}</p>}
    </section>
  );
}

function Tag({
  children,
  position,
}: {
  children: React.ReactNode;
  position: "left" | "right";
}) {
  return (
    <span
      className={`pointer-events-none absolute top-2 rounded bg-navy-950/80 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy-200 ${
        position === "left" ? "left-2" : "right-2"
      }`}
    >
      {children}
    </span>
  );
}

function Spinner() {
  return (
    <span className="absolute inset-0 grid place-items-center bg-navy-950/40">
      <Loader2 className="h-5 w-5 animate-spin text-navy-400" />
    </span>
  );
}
