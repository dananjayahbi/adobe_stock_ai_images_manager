"use client";

/**
 * Mode and threshold picker for the auto-fix panel.
 *
 * Two genuinely different jobs, so they are offered as two buttons rather than a
 * settings form:

 * - **Quick fix** applies the corrective recipe once. Fast; the right choice when
 *   the image is already close to compliant.
 * - **Deep fix** repeats with escalating correction strength until every
 *   auto-fixable score dimension reaches the target. This is the mode that can
 *   actually move the score, because the single-pass recipe recomputes identical
 *   strengths on each run and is therefore idempotent - which is exactly why a
 *   previous "fixed 4 issues" run left the percentage unchanged.
 *
 * The threshold is exposed because "good enough" is a judgement call: Adobe's bar
 * is 80%, but an operator may want to push further on a hero image or accept a
 * lower bar on a marginal one.
 */

import { Gauge, Zap } from "lucide-react";

import { Button } from "@/components/ui/Button";
import {
  AUTOFIX_DEFAULT_TARGET,
  AUTOFIX_MAX_TARGET,
  AUTOFIX_MIN_TARGET,
  type AutoFixMode,
} from "@/lib/api";

interface AutoFixControlsProps {
  mode: AutoFixMode;
  onModeChange: (mode: AutoFixMode) => void;
  target: number;
  onTargetChange: (target: number) => void;
  disabled: boolean;
  isRunning: boolean;
  onRun: () => void;
}

export default function AutoFixControls({
  mode,
  onModeChange,
  target,
  onTargetChange,
  disabled,
  isRunning,
  onRun,
}: AutoFixControlsProps) {
  const targetPercent = Math.round(target * 100);

  return (
    <div className="space-y-3">
      {/* Mode selector */}
      <div
        role="radiogroup"
        aria-label="Auto-fix mode"
        className="grid grid-cols-2 gap-2"
      >
        <ModeCard
          icon={Zap}
          title="Quick fix"
          description="One pass of the corrective recipe."
          selected={mode === "single"}
          disabled={disabled || isRunning}
          onSelect={() => onModeChange("single")}
        />
        <ModeCard
          icon={Gauge}
          title="Deep fix"
          description="Repeats and escalates until each fixable dimension hits the target."
          selected={mode === "adaptive"}
          disabled={disabled || isRunning}
          onSelect={() => onModeChange("adaptive")}
        />
      </div>

      {/* Threshold - only meaningful for the loop-based mode. */}
      {mode === "adaptive" ? (
        <div className="space-y-1.5 rounded border border-navy-800 bg-navy-950/50 p-2.5">
          <div className="flex items-center justify-between text-[11px]">
            <label htmlFor="autofix-target" className="text-navy-300">
              Target per dimension
            </label>
            <span className="font-mono tabular-nums text-navy-100">
              {targetPercent}%
              {targetPercent === Math.round(AUTOFIX_DEFAULT_TARGET * 100) ? (
                <span className="ml-1 text-navy-500">(default)</span>
              ) : null}
            </span>
          </div>
          <input
            id="autofix-target"
            type="range"
            min={AUTOFIX_MIN_TARGET * 100}
            max={AUTOFIX_MAX_TARGET * 100}
            step={5}
            value={targetPercent}
            disabled={disabled || isRunning}
            onChange={(event) => onTargetChange(Number(event.target.value) / 100)}
            className="w-full accent-violet-400"
          />
          <p className="text-[10px] text-navy-500">
            The loop stops when every fixable dimension reaches this. Adobe&apos;s
            acceptance bar is 80%.
          </p>
        </div>
      ) : null}

      <Button
        size="sm"
        variant="primary"
        disabled={disabled || isRunning}
        isLoading={isRunning}
        onClick={onRun}
        icon={isRunning ? undefined : mode === "adaptive" ? <Gauge className="h-3.5 w-3.5" aria-hidden /> : <Zap className="h-3.5 w-3.5" aria-hidden />}
      >
        {isRunning
          ? "Fixing…"
          : mode === "adaptive"
            ? `Deep fix to ${targetPercent}%`
            : "Quick fix & re-check"}
      </Button>
    </div>
  );
}

function ModeCard({
  icon: Icon,
  title,
  description,
  selected,
  disabled,
  onSelect,
}: {
  icon: typeof Zap;
  title: string;
  description: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      onClick={onSelect}
      className={
        "rounded-lg border p-2.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 " +
        (selected
          ? "border-violet-500/60 bg-violet-500/15"
          : "border-navy-800 bg-navy-950/50 hover:border-navy-600")
      }
    >
      <span className="flex items-center gap-1.5 text-[11px] font-semibold text-navy-100">
        <Icon className="h-3.5 w-3.5" aria-hidden />
        {title}
      </span>
      <span className="mt-1 block text-[10px] leading-snug text-navy-400">
        {description}
      </span>
    </button>
  );
}
