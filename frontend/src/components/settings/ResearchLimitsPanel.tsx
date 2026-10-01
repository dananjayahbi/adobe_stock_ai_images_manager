"use client";

import { Compass } from "lucide-react";

import { SettingsField, controlClass } from "@/components/settings/SettingsField";
import { cn } from "@/lib/cn";
import type { AppSettings } from "@/lib/settings";
import type { SettingsDraft } from "@/hooks/useAppSettings";

export interface ResearchLimitsPanelProps {
  settings: AppSettings;
  draft: SettingsDraft;
  setField: <K extends keyof SettingsDraft>(key: K, value: SettingsDraft[K]) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * How much research one turn may do.
 *
 * This exists because the limit was **not configurable at all** and its value was
 * measurably too small. A single `market_overview` call issues three searches, so
 * a run that checked two candidates for saturation and read one page had spent
 * eight calls before it scored anything — and a gated run must then score, maybe
 * look again for a stronger idea, and finally write prompts. The operator saw
 * "the agent reached its 10-call limit" and had no way to raise it.
 *
 * The copy states which calls are *free*, because the number is otherwise
 * confusing: the agent can visibly make more calls than the limit, since the
 * bookkeeping tools (`assess_validity`, `check_prompt_similarity`) are exempt.
 * That exemption is deliberate — charging for them once spent a run's final call
 * on scoring, leaving nothing to search with.
 */
export function ResearchLimitsPanel({
  settings,
  draft,
  setField,
  disabled = false,
  className,
}: ResearchLimitsPanelProps) {
  const value = Number.parseInt(draft.research_max_tool_calls, 10);
  const { min_tool_calls, max_tool_calls } = settings.bounds;
  const isOutOfRange =
    Number.isFinite(value) && (value < min_tool_calls || value > max_tool_calls);

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex items-start gap-2.5">
        <span className="mt-px shrink-0 text-accent-300">
          <Compass className="h-3.5 w-3.5" aria-hidden />
        </span>
        <div className="space-y-0.5">
          <h3 className="text-xs font-semibold text-navy-100">Research depth</h3>
          <p className="text-[11px] leading-relaxed text-navy-400">
            The research agent stops after this many searches and page reads, then
            answers with what it has gathered.
          </p>
        </div>
      </div>

      <SettingsField
        id="settings-research-calls"
        label="Research calls per turn"
        hint={
          isOutOfRange
            ? `Must be between ${min_tool_calls} and ${max_tool_calls}.`
            : "One market_overview call spends three of these. Recording a confidence score or checking prompts costs none."
        }
      >
        <input
          id="settings-research-calls"
          type="number"
          min={min_tool_calls}
          max={max_tool_calls}
          step="1"
          className={controlClass(isOutOfRange)}
          value={draft.research_max_tool_calls}
          disabled={disabled}
          onChange={(event) =>
            setField("research_max_tool_calls", event.target.value)
          }
        />
      </SettingsField>

      <p className="rounded-lg border border-navy-700/40 bg-navy-900/40 px-2.5 py-2 text-[11px] leading-relaxed text-navy-400">
        Higher is not automatically better: each extra call costs time and, on a
        metered search plan, quota. The default of{" "}
        <strong>{settings.research_max_tool_calls}</strong> covers a multi-source
        investigation of one idea. Raise it if runs routinely report hitting the
        limit.
      </p>
    </div>
  );
}
