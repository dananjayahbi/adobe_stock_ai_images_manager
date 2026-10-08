"use client";

import Badge from "@/components/ui/Badge";
import { STEP_BLURBS, STEP_LABELS, STEP_ORDER } from "@/lib/steps";
import type { MediaType } from "@/lib/types";

interface Props {
  mediaType: MediaType;
  selected: string[];
  onToggle: (key: string) => void;
}

/**
 * Wizard step 3 — choose which steps run (custom pipelines only).
 *
 * Rendering follows the canonical order regardless of selection order, so the
 * list reads the same as the processing page will execute it. Configs are not
 * edited here: the processing page owns configuration, keeping this modal a
 * fast, single-purpose choice.
 */
export default function StepsPicker({ mediaType, selected, onToggle }: Props) {
  const available = STEP_ORDER.filter((key) =>
    mediaType === "png"
      ? ["bg_remove", "ocr", "upscale", "metadata"].includes(key)
      : key !== "bg_remove"
  );

  return (
    <div className="space-y-3">
      <p className="text-sm text-ink-400">
        Toggle the steps this batch should run. They always execute in the
        order shown; pick as few or as many as you need.
      </p>

      <div className="grid gap-3">
        {available.map((key, index) => {
          const active = selected.includes(key);
          return (
            <button
              key={key}
              type="button"
              onClick={() => onToggle(key)}
              aria-pressed={active}
              className={`frame-card flex w-full items-start gap-4 px-5 py-4 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 ${
                active
                  ? "-translate-y-0.5 border-oxblood-500 ring-1 ring-oxblood-500"
                  : "hover:-translate-y-0.5"
              }`}
            >
              <span
                className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border font-stamp text-xs ${
                  active
                    ? "border-oxblood-500 bg-oxblood-500 text-parchment-50"
                    : "border-parchment-500 bg-parchment-100 text-ink-400"
                }`}
              >
                {index + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-base text-ink-800">
                    {STEP_LABELS[key]}
                  </span>
                  {key === "bg_remove" && <Badge tone="info">PNG only</Badge>}
                  {!active && <Badge>Skipped</Badge>}
                </span>
                <span className="mt-0.5 block text-sm text-ink-400">
                  {STEP_BLURBS[key]}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {selected.length === 0 && (
        <p className="text-sm text-oxblood-500" role="alert">
          Pick at least one step to continue.
        </p>
      )}
    </div>
  );
}
