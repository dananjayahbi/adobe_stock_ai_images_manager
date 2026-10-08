"use client";

import type { StepConfig, StepDefinition } from "@/lib/types";
import { STEP_FIELDS } from "@/lib/steps";

interface StepConfigFormProps {
  stepKey: string;
  config: StepConfig;
  onChange: (next: StepConfig) => void;
  disabled?: boolean;
}

/**
 * Config fields for one step.
 *
 * Field definitions are static (lib/steps.ts), but every value is validated on
 * save: a number field that is cleared falls back to the default rather than
 * writing `""` or `NaN` into the batch document.
 */
export default function StepConfigForm({
  stepKey,
  config,
  onChange,
  disabled = false,
}: StepConfigFormProps) {
  const fields = STEP_FIELDS[stepKey] ?? [];

  if (fields.length === 0) {
    return (
      <p className="text-sm italic text-ink-400">
        This step has no settings — it runs as-is.
      </p>
    );
  }

  const set = (key: string, value: string | number | boolean) => {
    onChange({ ...config, [key]: value });
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {fields.map((field) => {
        const id = `cfg-${stepKey}-${field.key}`;
        const value = config[field.key];

        return (
          <div key={field.key} className={field.type === "toggle" ? "flex items-start gap-3 sm:col-span-2" : ""}>
            {field.type === "toggle" ? (
              <>
                <input
                  id={id}
                  type="checkbox"
                  checked={Boolean(value)}
                  disabled={disabled}
                  onChange={(event) => set(field.key, event.target.checked)}
                  className="mt-0.5 h-4 w-4 accent-[#8b3a2f]"
                />
                <label htmlFor={id} className="select-none">
                  <span className="block text-sm font-medium text-ink-800">
                    {field.label}
                  </span>
                  {field.hint && (
                    <span className="block text-xs text-ink-400">{field.hint}</span>
                  )}
                </label>
              </>
            ) : (
              <div>
                <label htmlFor={id} className="label-caps mb-1 block">
                  {field.label}
                </label>
                {field.type === "select" ? (
                  <select
                    id={id}
                    value={String(value ?? "")}
                    disabled={disabled}
                    onChange={(event) => {
                      const option = field.options?.find(
                        (o) => String(o.value) === event.target.value
                      );
                      set(field.key, option ? option.value : event.target.value);
                    }}
                    className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60"
                  >
                    {(field.options ?? []).map((option) => (
                      <option key={String(option.value)} value={String(option.value)}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={id}
                    type="number"
                    value={typeof value === "number" ? value : ""}
                    min={field.min}
                    max={field.max}
                    step={field.step}
                    disabled={disabled}
                    onChange={(event) => {
                      const raw = event.target.value;
                      if (raw === "") return; // keep last valid while typing
                      const parsed = Number(raw);
                      if (Number.isFinite(parsed)) set(field.key, parsed);
                    }}
                    className="w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60"
                  />
                )}
                {field.hint && (
                  <p className="mt-1 text-xs text-ink-400">{field.hint}</p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
