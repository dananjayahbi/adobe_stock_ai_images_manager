"use client";

import { Check, Copy, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";
import { copyText } from "@/lib/clipboard";

export interface PromptCopyButtonProps {
  /** The prompt text to place on the clipboard. */
  value: string;
  /** Accessible name; the prompt title makes each button unique in a list. */
  label: string;
  /** Optional extra lines (e.g. the negative prompt) copied after the body. */
  suffix?: string | null;
  isBusy?: boolean;
  className?: string;
}

type CopyState = "idle" | "copied" | "failed";

/**
 * Copy-to-clipboard button for one prompt.
 *
 * Deliberately its own component rather than a reuse of the shared
 * `CopyButton`: this one lives inside a draggable card, so it must (a) stop
 * propagation on every pointer event, otherwise clicking it starts a drag or
 * selects the prompt, and (b) report a *failure*, because a clipboard denial is
 * otherwise indistinguishable from a successful copy — the operator would paste
 * stale text and never know.
 *
 * The icon is the whole control: a prompt block is a dense list item and a
 * text-labelled button would compete with Bind/Edit/Delete. The label is
 * carried by `aria-label` and `title` instead.
 */
export function PromptCopyButton({
  value,
  label,
  suffix = null,
  isBusy = false,
  className,
}: PromptCopyButtonProps) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    []
  );

  const handleCopy = useCallback(
    async (event: React.MouseEvent<HTMLButtonElement>) => {
      // The card is draggable and clickable; without this the click would also
      // select the prompt (and on some browsers arm a drag).
      event.stopPropagation();
      event.preventDefault();

      const payload = suffix ? `${value}\n\n${suffix}` : value;
      const ok = await copyText(payload);

      setState(ok ? "copied" : "failed");
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setState("idle"), ok ? 1500 : 2500);
    },
    [value, suffix]
  );

  const title =
    state === "copied"
      ? "Copied"
      : state === "failed"
        ? "Clipboard blocked — select the text and copy manually"
        : label;

  return (
    <button
      type="button"
      disabled={isBusy || !value}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={(event) => void handleCopy(event)}
      aria-label={label}
      title={title}
      className={cn(
        "inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-40",
        state === "copied" &&
          "border-emerald-500/50 bg-emerald-500/15 text-emerald-300",
        state === "failed" && "border-red-500/50 bg-red-500/15 text-red-300",
        state === "idle" &&
          "border-navy-700/60 bg-navy-800/60 text-navy-300 hover:border-accent-500/50 hover:text-accent-200",
        className
      )}
    >
      {state === "copied" ? (
        <Check className="h-3 w-3" aria-hidden />
      ) : state === "failed" ? (
        <X className="h-3 w-3" aria-hidden />
      ) : (
        <Copy className="h-3 w-3" aria-hidden />
      )}
    </button>
  );
}

export default PromptCopyButton;
