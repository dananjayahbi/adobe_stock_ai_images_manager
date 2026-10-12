"use client";

/**
 * The research workspace section: mode + run settings, the transcript (or its
 * empty state), the validity card, the prompt results, the composer, and the
 * saved-runs sidebar.
 *
 * Pure view of the page's state — every handler is owned by `page.tsx`, so the
 * live/replay distinction and the run lifecycle stay in one place. The editors
 * (system prompts, priority sources, tool budget) live behind the page's
 * Settings button, not in the workspace.
 */
import { FlaskConical } from "lucide-react";

import Composer from "@/components/prompts/Composer";
import ConfidenceCard from "@/components/prompts/ConfidenceCard";
import ModeSelector from "@/components/prompts/ModeSelector";
import PromptResultsCard, {
  type PromptDetail,
} from "@/components/prompts/PromptResultsCard";
import RunsSidebar from "@/components/prompts/RunsSidebar";
import RunSettingsPanel from "@/components/prompts/RunSettingsPanel";
import Transcript from "@/components/prompts/Transcript";
import Button from "@/components/ui/Button";
import {
  type FollowUpAction,
  type ResearchMessage,
  type ResearchMode,
  type ResearchRunSummary,
  type ResearchSettings,
} from "@/lib/research";
import { activityLine, type ResearchStreamState } from "@/lib/researchStream";

interface ResearchSectionProps {
  settings: ResearchSettings | null;
  runs: ResearchRunSummary[];
  isLoadingRuns: boolean;
  activeRunId: string | null;
  messages: ResearchMessage[];
  state: ResearchStreamState;
  mode: ResearchMode;
  onModeChange: (mode: ResearchMode) => void;
  count: number;
  onCountChange: (count: number) => void;
  validityCheck: boolean;
  onValidityChange: (value: boolean) => void;
  /** Streaming (or creating) a run — disables the run-scoped controls. */
  isBusy: boolean;
  /** Bodies already saved this session, marked "In library" on the cards. */
  acceptedBodies: string[];
  isSaving: boolean;
  onFollowUp: (action: FollowUpAction) => void;
  onSavePrompts: (bodies: string[], details: PromptDetail[]) => void;
  onSubmit: (message: string) => void;
  onStop: () => void;
  onNew: () => void;
  onSelectRun: (runId: string) => void;
  onDeleteRun: (runId: string) => void;
}

export default function ResearchSection({
  settings,
  runs,
  isLoadingRuns,
  activeRunId,
  messages,
  state,
  mode,
  onModeChange,
  count,
  onCountChange,
  validityCheck,
  onValidityChange,
  isBusy,
  acceptedBodies,
  isSaving,
  onFollowUp,
  onSavePrompts,
  onSubmit,
  onStop,
  onNew,
  onSelectRun,
  onDeleteRun,
}: ResearchSectionProps) {
  const activeMode = settings?.modes.find((entry) => entry.id === mode);
  const showCount = activeMode?.supports_count ?? false;
  const showValidity = activeMode?.supports_validity ?? false;
  // Ideas has no count knob — the operator says how many in the message.
  const countHint =
    !showCount && activeMode?.id === "ideas"
      ? "Say how many ideas you want in the message."
      : undefined;

  // One card per assessed idea (the ideas mode scores each idea separately);
  // falls back to the single `validity` so a one-assessment run — or a state
  // built before the list existed — still renders exactly as it did.
  const validityCards =
    state.validities.length > 0
      ? state.validities
      : state.validity
        ? [state.validity]
        : [];

  return (
    <section aria-label="Research workspace">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <p className="label-caps">Research workspace</p>
        {activeRunId && (
          <Button size="sm" variant="secondary" type="button" onClick={onNew}>
            New run
          </Button>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          {/* Mode + run settings */}
          <div className="frame-card px-5 py-4">
            <ModeSelector
              modes={settings?.modes ?? []}
              value={mode}
              onChange={onModeChange}
              disabled={isBusy}
            />
            {activeMode && (
              <p className="mt-3 text-sm leading-relaxed text-ink-400">
                {activeMode.description}
              </p>
            )}
            <div className="mt-4 border-t border-dashed border-parchment-400 pt-4">
              <RunSettingsPanel
                count={count}
                onCountChange={onCountChange}
                maxPrompts={settings?.max_prompts ?? 60}
                showCount={showCount}
                countHint={countHint}
                showValidity={showValidity}
                validityCheck={validityCheck}
                onValidityChange={onValidityChange}
                disabled={isBusy}
              />
            </div>
          </div>

          {/* Transcript (or its empty state) */}
          {messages.length > 0 || isBusy ? (
            <div className="frame-card px-5 py-4">
              <Transcript messages={messages} state={state} isLive={isBusy} />
            </div>
          ) : (
            <div className="frame-card px-6 py-12 text-center">
              <FlaskConical className="mx-auto h-7 w-7 text-brass-400" aria-hidden />
              <h2 className="mt-3 font-display text-xl text-ink-800">
                Start a research run
              </h2>
              <p className="mx-auto mt-1 max-w-md text-sm leading-relaxed text-ink-400">
                {activeMode?.description ??
                  "Pick a mode above, then describe the niche or idea you want to research."}
              </p>
            </div>
          )}

          {validityCards.length > 0 && (
            <div className="space-y-3">
              {validityCards.map((validity, index) => (
                <ConfidenceCard
                  key={`${index}-${validity.subject ?? ""}`}
                  validity={validity}
                  // The gate is one gate: its buttons ride on the latest
                  // card only, so N ideas do not render N copies of them.
                  followUpActions={
                    index === validityCards.length - 1
                      ? state.followUpActions
                      : []
                  }
                  onFollowUp={onFollowUp}
                  disabled={isBusy}
                />
              ))}
            </div>
          )}

          {state.prompts.length > 0 && (
            <PromptResultsCard
              prompts={state.prompts}
              acceptedBodies={acceptedBodies}
              isSaving={isSaving}
              summary={state.promptSummary}
              onSave={onSavePrompts}
            />
          )}

          {state.notices.length > 0 && (
            <div className="space-y-2">
              {state.notices.map((text, index) => (
                <p
                  key={index}
                  className="rounded-sm border border-brass-400/40 bg-brass-300/10 px-3 py-2 text-sm text-brass-300"
                >
                  {text}
                </p>
              ))}
            </div>
          )}

          <div className="frame-card px-5 py-4">
            <Composer
              onSubmit={onSubmit}
              onStop={onStop}
              isStreaming={isBusy}
              placeholder={
                activeMode
                  ? `Describe what you want from “${activeMode.label}”…`
                  : undefined
              }
              activity={isBusy ? activityLine(state) : undefined}
            />
          </div>
        </div>

        {/* Saved runs */}
        <div className="min-w-0 xl:sticky xl:top-[73px] xl:self-start">
          <div className="frame-card px-5 py-4">
            <RunsSidebar
              runs={runs}
              activeId={activeRunId}
              onSelect={onSelectRun}
              onNew={onNew}
              onDelete={onDeleteRun}
              isLoading={isLoadingRuns}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
