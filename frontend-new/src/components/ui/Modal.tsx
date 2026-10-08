"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Max-width class of the dialog panel. */
  width?: string;
  labelledBy?: string;
}

/**
 * Portal-based dialog.
 *
 * A portal is mandatory, not a style choice: any ancestor with a
 * `backdrop-filter` becomes the containing block for `position: fixed`, which
 * clamps the overlay to that ancestor's box (a sticky header would paint a
 * ~56px-tall "fullscreen" overlay behind the page). Portalled to
 * `document.body`, the overlay is always the real viewport; the mounted guard
 * keeps SSR happy because `document` does not exist on the server.
 */
export default function Modal({
  open,
  onClose,
  children,
  width = "max-w-2xl",
  labelledBy,
}: ModalProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
    >
      <div
        className="absolute inset-0 bg-ink-900/50"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`relative max-h-[90vh] w-full ${width} overflow-y-auto frame-card animate-fade-up`}
      >
        {children}
      </div>
    </div>,
    document.body
  );
}
