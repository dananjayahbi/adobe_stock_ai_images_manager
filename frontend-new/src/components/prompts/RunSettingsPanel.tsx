"use client";

import { hintClass, inputClass, labelClass } from "./fieldStyles";

interface RunSettingsPanelProps {
  /** Number of prompts wanted; only shown when the mode supports a count. */
  count: number;
  onCountChange: (value: number) => void;
  maxPrompts: number;
  showCount: boolean;
  /** Muted line shown where the count input would be, when there is none. */
  countHint?: string;
  /** Whether this mode can run the validity check. */
  showValidity: boolean;
  validityCheck: boolean;
  onValidityChange: (value: boolean) => void;
  disabled?: boolean;
}

/**
 * Per-run settings: the prompt count and the validity toggle.
 *
 * Both controls are gated on the active mode's capabilities (served by
 * `/api/research/settings`), so the UI never offers a knob the backend would
 * ignore. Rendered only when at least one applies, keeping the workspace free
 * of permanently-empty rows.
 */
export default function RunSettingsPanel({
  count,
  onCountChange,
  maxPrompts,
  showCount,
  countHint,
  showValidity,
  validityCheck,
  onValidityChange,
  disabled = false,
}: RunSettingsPanelProps) {
  if (!showCount && !showValidity) return null;

  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
      {!showCount && countHint && (
        <p className="max-w-[20rem] text-sm leading-relaxed text-ink-400">
          {countHint}
        </p>
      )}

      {showCount && (
        <div>
          <label htmlFor="research-count" className={labelClass}>
            Prompts to generate
          </label>
          <input
            id="research-count"
            type="number"
            min={1}
            max={maxPrompts}
            value={count}
            disabled={disabled}
            onChange={(event) => {
              const next = Number(event.target.value);
              if (Number.isFinite(next)) onCountChange(next);
            }}
            className={`${inputClass} max-w-[7rem]`}
          />
          <p className={hintClass}>
            Each prompt describes a different image (max {maxPrompts}).
          </p>
        </div>
      )}

      {showValidity && (
        <div className="min-w-[16rem] flex-1">
          <label className="label-caps mb-1 block">Validity check</label>
          <label className="flex cursor-pointer items-start gap-2 rounded-sm border border-parchment-500 bg-parchment-100 px-3 py-2">
            <input
              type="checkbox"
              checked={validityCheck}
              disabled={disabled}
              onChange={(event) => onValidityChange(event.target.checked)}
              className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-oxblood-500"
            />
            <span className="text-sm leading-snug text-ink-600">
              Score the idea first and wait for your decision before any prompts
              are written.
            </span>
          </label>
        </div>
      )}
    </div>
  );
}
