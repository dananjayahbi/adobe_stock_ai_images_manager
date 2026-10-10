"use client";

import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import ProgressBar from "@/components/ui/ProgressBar";
import StepConfigForm from "./StepConfigForm";
import type { BatchStep, StepProgress, StepStatus } from "@/lib/types";
import { STEP_LABELS, STEP_BLURBS } from "@/lib/steps";

interface StepCardProps {
  index: number;
  step: BatchStep;
  progress: StepProgress | null;
  /** Config can only change while the batch is not running. */
  editable: boolean;
  onConfigChange: (key: string, config: BatchStep["config"]) => void;
  /** Move this step one position up/down in the run order. */
  onMove?: (direction: -1 | 1) => void;
  /** Total steps — used to disable the down arrow on the last card. */
  totalSteps?: number;
}

const STATUS_TONE: Record<
  StepStatus,
  "neutral" | "success" | "warn" | "danger" | "info"
> = {
  pending: "neutral",
  running: "info",
  completed: "success",
  failed: "danger",
  cancelled: "warn",
};

/** One pipeline step: status, summary, and (when editable) its config. */
export default function StepCard({
  index,
  step,
  progress,
  editable,
  onConfigChange,
  onMove,
  totalSteps,
}: StepCardProps) {
  const [open, setOpen] = useState(false);
  const status: StepStatus = progress?.status ?? "pending";

  return (
    <li className="frame-card">
      <div className="flex items-start gap-4 px-5 py-4">
        <span
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border font-stamp text-sm ${
            status === "completed"
              ? "border-olive-500 bg-olive-500 text-ink-50"
              : status === "failed"
                ? "border-oxblood-500 bg-oxblood-500 text-ink-50"
                : status === "running"
                  ? "border-brass-400 bg-brass-300 text-ink-900"
                  : "border-parchment-500 bg-parchment-100 text-ink-400"
          }`}
          aria-hidden="true"
        >
          {status === "completed" ? "✓" : status === "failed" ? "✕" : index + 1}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-lg text-ink-800">
              {STEP_LABELS[step.key] ?? step.key}
            </h3>
            <Badge tone={STATUS_TONE[status]}>{status}</Badge>
          </div>
          <p className="mt-0.5 text-sm text-ink-400">
            {STEP_BLURBS[step.key] ?? ""}
          </p>

          {progress?.message && (
            <p className="mt-1.5 font-stamp text-[11px] text-ink-600">
              {/* The backend folds counts into the message — render it as-is. */}
              {progress.message}
            </p>
          )}

          {status === "running" && (
            <div className="mt-2 max-w-xs">
              <ProgressBar value={null} tone="brass" />
            </div>
          )}
        </div>

        {editable && onMove && (
          <span className="flex shrink-0 flex-col gap-1">
            <button
              type="button"
              onClick={() => onMove(-1)}
              disabled={index === 0}
              aria-label={`Move ${STEP_LABELS[step.key] ?? step.key} up`}
              className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 text-xs text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-30"
            >
              ↑
            </button>
            <button
              type="button"
              onClick={() => onMove(1)}
              disabled={totalSteps != null && index >= totalSteps - 1}
              aria-label={`Move ${STEP_LABELS[step.key] ?? step.key} down`}
              className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 text-xs text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-30"
            >
              ↓
            </button>
          </span>
        )}

        {editable && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open ? "Done" : "Configure"}
          </Button>
        )}
      </div>

      {open && editable && (
        <div className="border-t border-dashed border-parchment-400 bg-parchment-100/60 px-5 py-4">
          <StepConfigForm
            stepKey={step.key}
            config={step.config}
            onChange={(next) => onConfigChange(step.key, next)}
          />
        </div>
      )}
    </li>
  );
}
