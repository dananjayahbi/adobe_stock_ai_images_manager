"use client";

import {
  Ban,
  CheckCircle2,
  Database,
  Images,
  Maximize2,
  ScanText,
  SlidersHorizontal,
  Tags,
} from "lucide-react";

import {
  STAGE_DEFINITIONS,
  stageNumber,
  type PipelineStage,
} from "@/lib/stages";

const STAGE_ICONS: Record<string, typeof ScanText> = {
  collector: Database,
  ocr: ScanText,
  upscale: Maximize2,
  refine: SlidersHorizontal,
  compatibility: CheckCircle2,
  metadata: Tags,
  gallery: Images,
};

interface StageRailProps {
  activeStage: PipelineStage;
  counts: Partial<Record<PipelineStage, number>>;
  onSelectStage: (stage: PipelineStage) => void;
}

/**
 * Vertical stage navigation.
 *
 * Each of the seven stages shows its record count and expands into the concrete
 * sub-states it owns (e.g. OCR splits into "clear" and "rejected"), because a
 * rejected image needs a different response than one that merely cleared.
 */
export default function StageRail({
  activeStage,
  counts,
  onSelectStage,
}: StageRailProps) {
  return (
    <nav aria-label="Pipeline stages" className="space-y-1.5">
      {STAGE_DEFINITIONS.map((definition) => {
        const Icon = STAGE_ICONS[definition.key] ?? Database;
        const total = definition.stages.reduce(
          (sum, stage) => sum + (counts[stage] ?? 0),
          0
        );
        const isActive = definition.stages.includes(activeStage);

        return (
          <div
            key={definition.key}
            className={`rounded-lg border transition-colors ${
              isActive
                ? "border-sky-500/50 bg-sky-500/10"
                : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-700"
            }`}
          >
            <button
              type="button"
              onClick={() => onSelectStage(definition.stages[0])}
              aria-current={isActive ? "step" : undefined}
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left"
            >
              <span
                className={`grid h-7 w-7 shrink-0 place-items-center rounded-md text-xs font-bold ${
                  isActive
                    ? "bg-sky-500/20 text-sky-300"
                    : "bg-zinc-800 text-zinc-400"
                }`}
              >
                {definition.number}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <Icon
                    className={`h-3.5 w-3.5 shrink-0 ${
                      isActive ? "text-sky-300" : "text-zinc-500"
                    }`}
                  />
                  <span
                    className={`truncate text-sm font-medium ${
                      isActive ? "text-zinc-100" : "text-zinc-300"
                    }`}
                  >
                    {definition.name}
                  </span>
                </span>
              </span>

              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${
                  total > 0
                    ? "bg-zinc-700/70 text-zinc-200"
                    : "bg-zinc-800/60 text-zinc-600"
                }`}
              >
                {total}
              </span>
            </button>

            {/* Sub-state breakdown, only when a stage owns more than one. */}
            {definition.stages.length > 1 && (
              <div className="flex gap-1 border-t border-zinc-800/70 px-2 py-1.5">
                {definition.stages.map((stage) => {
                  const count = counts[stage] ?? 0;
                  const isRejected =
                    stage === "OCR_REJECTED" || stage === "INCOMPATIBLE";
                  const isSubActive = stage === activeStage;

                  return (
                    <button
                      key={stage}
                      type="button"
                      onClick={() => onSelectStage(stage)}
                      aria-current={isSubActive ? "step" : undefined}
                      className={`flex flex-1 items-center justify-center gap-1 rounded px-1.5 py-1 text-[11px] font-medium transition-colors ${
                        isSubActive
                          ? isRejected
                            ? "bg-amber-500/20 text-amber-200"
                            : "bg-emerald-500/20 text-emerald-200"
                          : "text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                      }`}
                    >
                      {isRejected && <Ban className="h-3 w-3" />}
                      <span className="truncate">
                        {stage === "OCR_CLEAR"
                          ? "Clear"
                          : stage === "OCR_REJECTED"
                            ? "Rejected"
                            : stage === "COMPATIBLE"
                              ? "Passed"
                              : "Failed"}
                      </span>
                      <span className="tabular-nums opacity-70">{count}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </nav>
  );
}
