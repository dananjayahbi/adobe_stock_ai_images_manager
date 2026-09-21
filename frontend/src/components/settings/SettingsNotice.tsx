"use client";

import { AlertCircle, CheckCircle2, Eye, Info, Loader2 } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type SettingsNoticeTone = "info" | "success" | "error" | "busy";

const TONES: Record<SettingsNoticeTone, { shell: string; icon: ReactNode }> = {
  info: {
    shell: "border-navy-700/60 bg-navy-850/50 text-navy-200",
    icon: <Info className="h-3.5 w-3.5 text-navy-300" aria-hidden />,
  },
  success: {
    shell: "border-emerald-500/35 bg-emerald-500/10 text-emerald-100",
    icon: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" aria-hidden />,
  },
  error: {
    shell: "border-red-500/40 bg-red-500/10 text-red-100",
    icon: <AlertCircle className="h-3.5 w-3.5 text-red-300" aria-hidden />,
  },
  busy: {
    shell: "border-accent-500/35 bg-accent-500/10 text-accent-100",
    icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-300" aria-hidden />,
  },
};

export interface SettingsNoticeProps {
  tone: SettingsNoticeTone;
  title?: ReactNode;
  children?: ReactNode;
}

/** Inline feedback strip used for validation, connection tests, and hints. */
export function SettingsNotice({ tone, title, children }: SettingsNoticeProps) {
  const { shell, icon } = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-[11px] leading-relaxed",
        shell
      )}
    >
      <span className="mt-px shrink-0">{icon}</span>
      <div className="min-w-0 space-y-0.5">
        {title ? <p className="font-medium">{title}</p> : null}
        {children ? <div className="break-words">{children}</div> : null}
      </div>
    </div>
  );
}

export interface VisionModelNoteProps {
  className?: string;
}

/**
 * The vision-only warning.
 *
 * This is not a nicety: every LLM call in the app attaches an image, so a
 * text-only model will fail every request with an opaque provider error. The
 * note states the requirement and names the capability to look for.
 */
export function VisionModelNote({ className }: VisionModelNoteProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5",
        className
      )}
    >
      <span className="mt-px shrink-0 text-amber-300">
        <Eye className="h-3.5 w-3.5" aria-hidden />
      </span>
      <div className="space-y-1 text-[11px] leading-relaxed text-amber-100">
        <p className="font-medium">Vision-capable models only</p>
        <p className="text-amber-100/80">
          Every AI feature here sends the image itself, so the model must accept
          image input. A text-only model will fail every request. Check the
          provider&apos;s model card for a vision, multimodal, or image-input
          capability before saving.
        </p>
      </div>
    </div>
  );
}

export default SettingsNotice;
