"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { cn } from "@/lib/cn";

export type ModalSize = "sm" | "md" | "lg" | "xl";

const SIZES: Record<ModalSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-4xl",
};

/**
 * Stacking layer for the dialog.
 *
 * Above the app header (`z-40`) and the stage dropdown (`z-50`). The portal
 * below is what makes this reliable, but an explicit layer keeps the intent
 * obvious and survives a future change that gives the header a higher z-index.
 */
const OVERLAY_Z = "z-[100]";

export interface ModalProps {
  isOpen: boolean;
  title: ReactNode;
  /** Short line under the title explaining what the dialog configures. */
  description?: ReactNode;
  icon?: ReactNode;
  onClose: () => void;
  size?: ModalSize;
  /** Footer actions, right-aligned. */
  footer?: ReactNode;
  children: ReactNode;
  /** Blocks Escape/backdrop dismissal while a save or test is in flight. */
  isBusy?: boolean;
}

/**
 * The app's modal shell.
 *
 * `ConfirmDialog` stays the destructive-action shortcut; this is the general
 * dialog for anything that needs a form. Both follow the same interaction
 * contract: Escape and a backdrop click close it, the first focusable control
 * receives focus on open, and focus returns to the trigger on close so keyboard
 * navigation is not lost.
 *
 * The dialog is rendered into a **portal on `document.body`** rather than in
 * place. This is not cosmetic: `position: fixed` is resolved against the
 * nearest ancestor that establishes a containing block, and a `backdrop-filter`
 * (which the sticky header uses) creates one. Left inline, the overlay was
 * clamped to the header's 56px box and painted inside the header's `z-40`
 * stacking context, so it appeared behind the page content. A portal removes it
 * from every ancestor's containing block and stacking context.
 */
export function Modal({
  isOpen,
  title,
  description,
  icon,
  onClose,
  size = "md",
  footer,
  children,
  isBusy = false,
}: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<Element | null>(null);
  // `document` does not exist during SSR, so the portal is only mounted after
  // the first client render.
  const [isMounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Latest-value refs. The effect below deliberately depends only on `isOpen`:
  // if it also depended on `isBusy` or `onClose`, the cleanup would run on
  // every busy toggle or parent re-render, restoring focus to the trigger and
  // then re-focusing the first field - which yanks the caret out of whatever
  // the operator is typing into.
  const onCloseRef = useRef(onClose);
  const isBusyRef = useRef(isBusy);
  onCloseRef.current = onClose;
  isBusyRef.current = isBusy;

  useEffect(() => {
    if (!isOpen) return;

    returnFocusRef.current = document.activeElement;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !isBusyRef.current) {
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;

      // Trap Tab inside the dialog so a long form cannot tab into the page
      // behind it, which would be invisible and disorienting.
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);

    // Prevent the page behind the dialog from scrolling. The scrollbar's width
    // is replaced with padding, otherwise removing it reflows the page and the
    // content visibly jumps as the dialog opens.
    const body = document.body;
    const previousOverflow = body.style.overflow;
    const previousPaddingRight = body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    body.style.overflow = "hidden";
    if (scrollbarWidth > 0) {
      const currentPadding = parseFloat(getComputedStyle(body).paddingRight) || 0;
      body.style.paddingRight = `${currentPadding + scrollbarWidth}px`;
    }

    // Move focus into the dialog once it has rendered.
    const timer = window.setTimeout(() => {
      const target = panelRef.current?.querySelector<HTMLElement>(
        'input:not([type="hidden"]), textarea, select, button'
      );
      target?.focus();
    }, 0);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      body.style.overflow = previousOverflow;
      body.style.paddingRight = previousPaddingRight;
      window.clearTimeout(timer);
      (returnFocusRef.current as HTMLElement | null)?.focus?.();
    };
  }, [isOpen]);

  if (!isOpen || !isMounted) return null;

  return createPortal(
    <div
      className={cn(
        "fixed inset-0 flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm sm:items-center",
        OVERLAY_Z
      )}
      role="dialog"
      aria-modal="true"
      aria-label={typeof title === "string" ? title : undefined}
      onClick={() => !isBusy && onClose()}
    >
      <div
        ref={panelRef}
        className={cn(
          "my-auto w-full overflow-hidden rounded-xl border border-navy-800 bg-navy-950 shadow-raised",
          SIZES[size]
        )}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-3 border-b border-navy-800 px-5 py-4">
          {icon ? (
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-accent-500/25 bg-accent-500/10 text-accent-300">
              {icon}
            </span>
          ) : null}
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-navy-50">{title}</h2>
            {description ? (
              <p className="mt-1 text-xs leading-relaxed text-navy-300">{description}</p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isBusy}
            aria-label="Close dialog"
            className="rounded-md p-1 text-navy-400 transition-colors hover:text-navy-100 disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-5 py-4">{children}</div>

        {footer ? (
          <div className="flex flex-wrap justify-end gap-2 border-t border-navy-800 bg-navy-900/50 px-5 py-3">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

export default Modal;
