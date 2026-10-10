"use client";

import Badge from "@/components/ui/Badge";
import { MEDIA_STEPS, STEP_BLURBS, STEP_LABELS, STEP_ORDER } from "@/lib/steps";
import type { MediaType } from "@/lib/types";
import SaveAsProfileControl from "./SaveAsProfileControl";

interface Props {
  mediaType: MediaType;
  /** Selected step keys, **in run order**. */
  selected: string[];
  onToggle: (key: string) => void;
  /** Move a selected step one position up/down in the run order. */
  onMove: (key: string, direction: -1 | 1) => void;
  onRemove: (key: string) => void;
}

/**
 * Wizard step 3 — choose which steps run (custom pipelines only), and in
 * what order.
 *
 * Two halves: the available steps (canonical catalog order, click to toggle)
 * and the **run order** list, which is exactly the order the batch will
 * execute in. The server stores the list as given, so moving a step here is
 * the same move the runner honours.
 */
export default function StepsPicker({
  mediaType,
  selected,
  onToggle,
  onMove,
  onRemove,
}: Props) {
  const available = STEP_ORDER.filter((key) =>
    MEDIA_STEPS[mediaType].includes(key)
  );

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-400">
        Toggle the steps this batch should run, then arrange them in the run
        order beside the list. Pick as few or as many as you need.
      </p>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* Available steps — click to toggle */}
        <div className="grid content-start gap-3">
          {available.map((key) => {
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
                      ? "border-oxblood-500 bg-oxblood-500 text-ink-50"
                      : "border-parchment-500 bg-parchment-100 text-ink-400"
                  }`}
                >
                  {active ? selected.indexOf(key) + 1 : "–"}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-display text-base text-ink-800">
                      {STEP_LABELS[key]}
                    </span>
                    {key === "bg_remove" && <Badge tone="info">PNG only</Badge>}
                    {key === "pure_white" && (
                      <Badge tone="info">White bg photos</Badge>
                    )}
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

        {/* Run order — the operator's arrangement */}
        <div className="frame-card h-fit px-4 py-4">
          <p className="label-caps mb-3">Run order</p>
          {selected.length === 0 ? (
            <p className="text-sm italic text-ink-400">
              No steps yet — toggle one on the left.
            </p>
          ) : (
            <ol className="space-y-2">
              {selected.map((key, index) => (
                <li
                  key={key}
                  className="flex items-center gap-3 rounded-sm border border-parchment-400 bg-parchment-100 px-3 py-2"
                >
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-oxblood-500 bg-oxblood-500 font-stamp text-[11px] text-ink-50">
                    {index + 1}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-800">
                    {STEP_LABELS[key] ?? key}
                  </span>
                  <span className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => onMove(key, -1)}
                      disabled={index === 0}
                      aria-label={`Move ${STEP_LABELS[key] ?? key} up`}
                      className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 text-xs text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => onMove(key, 1)}
                      disabled={index === selected.length - 1}
                      aria-label={`Move ${STEP_LABELS[key] ?? key} down`}
                      className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 text-xs text-ink-600 transition-colors hover:border-brass-400 hover:text-ink-900 disabled:cursor-not-allowed disabled:opacity-30"
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      onClick={() => onRemove(key)}
                      aria-label={`Remove ${STEP_LABELS[key] ?? key}`}
                      className="flex h-6 w-6 items-center justify-center rounded-sm border border-parchment-500 text-xs text-ink-600 transition-colors hover:border-oxblood-500 hover:text-oxblood-400"
                    >
                      ✕
                    </button>
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {selected.length === 0 && (
        <p className="text-sm text-oxblood-400" role="alert">
          Pick at least one step to continue.
        </p>
      )}

      <SaveAsProfileControl mediaType={mediaType} selected={selected} />
    </div>
  );
}
