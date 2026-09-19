"use client";

import { AlertCircle, CheckCircle2, X } from "lucide-react";

interface BannerProps {
  tone: "error" | "success" | "info";
  children: React.ReactNode;
  onDismiss?: () => void;
  icon?: React.ReactNode;
}

const TONE_STYLES: Record<BannerProps["tone"], string> = {
  error: "border-red-500/40 bg-red-500/10 text-red-200",
  success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-200",
};

const TONE_ICONS: Record<BannerProps["tone"], React.ReactNode> = {
  error: <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />,
  success: <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />,
  info: <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />,
};

/** Dismissible inline message used across the stage workspace. */
export default function StageBanner({
  tone,
  children,
  onDismiss,
  icon,
}: BannerProps) {
  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-4 py-3 text-sm ${TONE_STYLES[tone]}`}
      role={tone === "error" ? "alert" : "status"}
    >
      {icon ?? TONE_ICONS[tone]}
      <span className="flex-1 whitespace-pre-wrap">{children}</span>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Dismiss message"
          className="rounded p-0.5 opacity-70 transition-opacity hover:opacity-100"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}
