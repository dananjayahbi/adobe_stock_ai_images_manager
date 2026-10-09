"use client";

import { useCallback, useRef, useState } from "react";

interface SlideConfirmProps {
  /** Fired once the handle reaches the end of the track. */
  onConfirm: () => void;
  /** Track label, e.g. "Slide to delete". */
  label: string;
  /** Tone accent for the filled track. */
  tone?: "danger" | "primary";
  disabled?: boolean;
}

/**
 * Slide-to-confirm control — the guard against accidental destructive clicks.
 *
 * Pointer events only (not mouse events) so it works with touch and pen. The
 * handle snaps back on release unless it clears 92% of the track, and a
 * keyboard user can confirm with Enter/Space, which the parent must also
 * gate behind an explicit focus — the intent is friction, not a trap.
 */
export default function SlideConfirm({
  onConfirm,
  label,
  tone = "danger",
  disabled = false,
}: SlideConfirmProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [progress, setProgress] = useState(0); // 0..1
  const [done, setDone] = useState(false);
  const dragging = useRef(false);

  const fill =
    tone === "danger" ? "bg-rust-500/70" : "bg-oxblood-500/70";

  const updateFrom = useCallback((clientX: number) => {
    const track = trackRef.current;
    if (!track) return 0;
    const rect = track.getBoundingClientRect();
    const handleWidth = 40;
    const usable = rect.width - handleWidth;
    const ratio = usable > 0 ? (clientX - rect.left - handleWidth / 2) / usable : 0;
    const next = Math.min(1, Math.max(0, ratio));
    setProgress(next);
    return next;
  }, []);

  const settle = useCallback(() => {
    if (progress >= 0.92) {
      setProgress(1);
      setDone(true);
      onConfirm();
      // Reset after the action so the control is reusable if it survives.
      window.setTimeout(() => {
        setProgress(0);
        setDone(false);
      }, 600);
    } else {
      setProgress(0);
    }
  }, [progress, onConfirm]);

  if (disabled) {
    return (
      <div
        className="relative h-11 w-full overflow-hidden rounded-sm border border-parchment-500 bg-parchment-200"
        aria-hidden="true"
      >
        <p className="flex h-full items-center justify-center font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
          {label}
        </p>
      </div>
    );
  }

  return (
    <div
      ref={trackRef}
      className={`relative h-11 w-full select-none overflow-hidden rounded-sm border ${
        tone === "danger" ? "border-rust-500/60" : "border-oxblood-500/60"
      } bg-parchment-100`}
      role="slider"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
      tabIndex={0}
      onPointerDown={(event) => {
        if (done) return;
        dragging.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        updateFrom(event.clientX);
      }}
      onPointerMove={(event) => {
        if (!dragging.current) return;
        updateFrom(event.clientX);
      }}
      onPointerUp={() => {
        if (!dragging.current) return;
        dragging.current = false;
        settle();
      }}
      onPointerCancel={() => {
        dragging.current = false;
        setProgress(0);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          setProgress(1);
          setDone(true);
          onConfirm();
        }
      }}
    >
      <div
        className={`absolute inset-y-0 left-0 ${fill} transition-none`}
        style={{ width: `${progress * 100}%` }}
        aria-hidden="true"
      />
      <p className="pointer-events-none absolute inset-0 flex items-center justify-center pl-10 font-stamp text-[11px] uppercase tracking-[0.18em] text-ink-600">
        {done ? "Confirmed" : label}
      </p>
      <div
        className="absolute top-0.5 flex h-9 w-10 items-center justify-center rounded-sm border border-parchment-500 bg-parchment-50 shadow-card"
        style={{ left: `calc(${progress} * (100% - 40px))` }}
        aria-hidden="true"
      >
        <span className="text-ink-800">{done ? "✓" : "→"}</span>
      </div>
    </div>
  );
}
