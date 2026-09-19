"use client";

import { Check, Copy } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { copyText } from "@/lib/clipboard";

interface CopyButtonProps {
  value: string;
  label?: string;
  /** Render only the icon, hiding the text label. */
  iconOnly?: boolean;
  className?: string;
}

/** Small button that copies a value and briefly confirms success. */
export default function CopyButton({
  value,
  label = "Copy",
  iconOnly = false,
  className = "",
}: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    []
  );

  const handleCopy = useCallback(async () => {
    const ok = await copyText(value);
    if (!ok) return;
    setCopied(true);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 1500);
  }, [value]);

  return (
    <button
      type="button"
      onClick={() => void handleCopy()}
      aria-label={iconOnly ? label : undefined}
      title={label}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors ${
        copied
          ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
          : "border-navy-700 text-navy-200 hover:border-navy-400 hover:text-navy-50"
      } ${className}`}
    >
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      {!iconOnly && (copied ? "Copied" : label)}
    </button>
  );
}
