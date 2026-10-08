"use client";

import { FlaskConical, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import ConfidenceCard from "@/components/research/ConfidenceCard";
import ContextWindowBar from "@/components/research/ContextWindowBar";
import FollowUpActions from "@/components/research/FollowUpActions";
import HouseStyleEditor from "@/components/research/HouseStyleEditor";
import ModeSelector, { ModeDescription } from "@/components/research/ModeSelector";
import PrioritySourcesPanel from "@/components/research/PrioritySourcesPanel";
import PromptResultCard, { type PromptDetail } from "@/components/research/PromptResultCard";
import ResearchComposer from "@/components/research/ResearchComposer";
import ResearchThreadList from "@/components/research/ResearchThreadList";
import ResearchTranscript from "@/components/research/ResearchTranscript";
import RunSettingsPanel from "@/components/research/RunSettingsPanel";
import SourcesPanel from "@/components/research/SourcesPanel";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { PageShell } from "@/components/shell/PageShell";
import { useHouseStyle } from "@/hooks/useHouseStyle";
import { useResearchStream } from "@/hooks/useResearchStream";
import {
  acceptResearchPrompts,
  createResearchRun,
  deleteResearchRun,
  fetchResearchRun,
  fetchResearchRuns,
  fetchResearchSettings,
  type FollowUpAction,
  type ResearchMessage,
  type ResearchMode,
  type ResearchRunSummary,
  type ResearchSettings,
} from "@/lib/research";
import { activityLine, reduceEvents, saveablePrompts } from "@/lib/researchStream";

/** Quick-start prompts per mode, so the operator sees what a good input looks like. */
const SUGGESTIONS: Record<ResearchMode, string[]> = {
  static: [
    "A wide shot of a robotic sorting facility at dusk",
    "Solar panel maintenance on a rooftop at golden hour",
  ],
  batch: [
    "Automated logistics warehouses, 6 prompts",
    "Sustainable vertical farming, 8 prompts",
  ],
  research: [
    "Automated logistics warehouses — is it saturated?",
    "Offshore wind turbine maintenance crews",
  ],
  ideas: [
    "Research the best possible ideas and tell me",
    "Which industrial niches are underserved?",
  ],
};

const PLACEHOLDERS: Record<ResearchMode, string> = {
  static: "Describe what you want — a hint is enough…",
  batch: "Describe the niche and how many prompts you need…",
  research: "Describe the idea or niche to investigate…",
  ideas: "Ask what is worth pursuing…",
};

/**
 * Prompt Research — the agentic prompt-research workspace.
 *
 * A two-pane page: the conversation on the left, the research threads on the
 * right. The transcript is the primary surface because the feature's value is the
 * *process* — what the agent searched, what it found, how confident it is — not
 * just the prompts at the end.
 *
 * Everything the operator needs is on this page: mode, run settings, the live
 * agent activity, the confidence scorecard, and the prompts with a one-click
 * route into the Prompt Library. That is the point of the feature — the operator
 * should not have to leave the app to research and write a prompt.
 */
export default function ResearchPage() {
  const [settings, setSettings] = useState<ResearchSettings | null>(null);
  const [threads, setThreads] = useState<ResearchRunSummary[]>([]);
  const [isLoadingThreads, setLoadingThreads] = useState(true);

  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ResearchMessage[]>([]);

  const [mode, setMode] = useState<ResearchMode>("static");
  const [count, setCount] = useState(1);
  const [validityCheck, setValidityCheck] = useState(false);

  // The house standard and rules live server-side (see `useHouseStyle`), so the
  // page owns them only to hand the style to a run. Kept in one hook rather than
  // two local `useState`s because the editor and the run must never disagree
  // about what text is current — that disagreement was the original bug.
  const houseStyle = useHouseStyle();

  const [acceptedBodies, setAcceptedBodies] = useState<string[]>([]);
  const [isSaving, setSaving] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const stream = useResearchStream();
  const { state } = stream;

  // The thread list is refreshed after each completed turn, not on a timer: a
  // research turn takes a minute, and polling would fight the stream for the
  // same information.
  const loadThreads = useCallback(async () => {
    try {
      setThreads(await fetchResearchRuns());
    } catch (error) {
      setPageError((error as Error).message);
    } finally {
      setLoadingThreads(false);
    }
  }, []);

  useEffect(() => {
    void loadThreads();
  }, [loadThreads]);

  useEffect(() => {
    void (async () => {
      try {
        setSettings(await fetchResearchSettings());
      } catch (error) {
        setPageError((error as Error).message);
      }
    })();
  }, []);

  // When a turn finishes, refresh the thread list so its title, prompt count and
  // score badge are current.
  const finishedRunRef = useRef<string | null>(null);
  useEffect(() => {
    if (!state.finished || !activeRunId) return;
    if (finishedRunRef.current === activeRunId) return;
    finishedRunRef.current = activeRunId;
    void loadThreads();
  }, [state.finished, activeRunId, loadThreads]);

  const activeMode = settings?.modes.find((entry) => entry.id === mode);
  const showCount = activeMode?.supports_count ?? false;
  const showValidity = activeMode?.supports_validity ?? false;

  /** Adopt a conversation: load its stored transcript and replayed result. */
  const openRun = useCallback(
    async (runId: string) => {
      setPageError(null);
      try {
        const run = await fetchResearchRun(runId);
        setActiveRunId(run.id);
        setMessages(run.messages ?? []);
        setMode((run.mode as ResearchMode) ?? "static");
        setValidityCheck(Boolean(run.settings?.validity_check));
        setCount(Number(run.settings?.count ?? 1) || 1);
        // The style instruction is deliberately NOT adopted from the run.
        //
        // It used to be, which meant opening an old thread overwrote the box with
        // whatever that run happened to use — and since the box was also the only
        // place the text lived, browsing conversations silently rewrote the
        // operator's house standard. A run's style is a snapshot *of* the house
        // standard, never the source of it.
        setAcceptedBodies(
          Array.isArray(run.result?.accepted_prompt_ids)
            ? // The stored ids identify the prompts; the *bodies* are what the
              // cards compare against, so the ids are resolved against the run's
              // own prompt list.
              (run.result?.prompts ?? [])
                .filter((prompt) =>
                  (run.result?.accepted_prompt_ids ?? []).includes(String(prompt.index))
                )
                .map((prompt) => prompt.body)
            : []
        );
        // Replay the stored transcript through the same reducer the live stream
        // uses, so a reloaded view and a live one cannot disagree.
        const replayed = reduceEvents(run.events ?? []);
        stream.reset({
          ...replayed,
          prompts: run.result?.prompts ?? replayed.prompts,
          sources: run.result?.sources ?? replayed.sources,
          validity: run.result?.validity ?? replayed.validity,
          notices: run.result?.notices ?? replayed.notices,
          isStreaming: false,
          finished: true,
        });
      } catch (error) {
        setPageError((error as Error).message);
      }
    },
    [stream]
  );

  /** Start a new conversation and stream its opening turn. */
  const startNew = useCallback(
    async (message: string) => {
      setPageError(null);
      setNotice(null);
      setAcceptedBodies([]);
      stream.reset({ isStreaming: true });

      // Settle the house style before the run captures it: the run sends the
      // current text, so a pending keystroke must be saved (and the saved value
      // read back) or the run would carry a style the operator never saw stored.
      houseStyle.markRunStarted();
      await houseStyle.flush();
      const styleForRun = houseStyle.currentStyle();

      let runId: string;
      try {
        // Created *without* running, so the first turn streams and the operator
        // sees the agent work from the first second.
        const created = await createResearchRun({
          message,
          mode,
          count: showCount ? count : 1,
          styleInstruction: styleForRun,
          validityCheck: showValidity ? validityCheck : false,
        });
        runId = created.id;
        setActiveRunId(created.id);
        setMessages(created.messages ?? []);
      } catch (error) {
        setPageError((error as Error).message);
        stream.reset();
        return;
      }

      await stream.send({
        runId,
        count: showCount ? count : undefined,
        validityCheck: showValidity ? validityCheck : undefined,
      });
      await loadThreads();
    },
    [count, houseStyle, loadThreads, mode, showCount, showValidity, stream, validityCheck]
  );

  /** Continue the active conversation. */
  const continueRun = useCallback(
    async (message: string) => {
      if (!activeRunId) return;
      setPageError(null);
      setNotice(null);
      // Append the operator's turn immediately so the transcript reads correctly
      // while the reply streams in.
      setMessages((current) => [...current, { role: "user", content: message }]);
      await stream.send({
        runId: activeRunId,
        message,
        count: showCount ? count : undefined,
        validityCheck: showValidity ? validityCheck : undefined,
      });
      await loadThreads();
    },
    [activeRunId, count, loadThreads, showCount, showValidity, stream, validityCheck]
  );

  const handleSubmit = useCallback(
    async (message: string) => {
      if (activeRunId) await continueRun(message);
      else await startNew(message);
    },
    [activeRunId, continueRun, startNew]
  );

  /** A confidence-score button: send its canned message through the chat path. */
  const handleFollowUp = useCallback(
    async (action: FollowUpAction) => {
      await continueRun(action.message);
    },
    [continueRun]
  );

  const handleSave = useCallback(
    async (bodies: string[], details: PromptDetail[]) => {
      if (!activeRunId || bodies.length === 0) return;
      setSaving(true);
      setPageError(null);
      try {
        const outcome = await acceptResearchPrompts(activeRunId, bodies, {
          tags: [mode, "prompt-research"],
          details,
        });
        setAcceptedBodies((current) => [...current, ...bodies]);
        setNotice(
          outcome.count > 0
            ? `Added ${outcome.count} prompt${outcome.count === 1 ? "" : "s"} to the Prompt Library as drafts.`
            : "Those prompts are already in the library."
        );
      } catch (error) {
        setPageError((error as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [activeRunId, mode]
  );

  const handleDelete = useCallback(
    async (runId: string) => {
      try {
        await deleteResearchRun(runId);
        if (runId === activeRunId) {
          setActiveRunId(null);
          setMessages([]);
          stream.reset();
        }
        await loadThreads();
      } catch (error) {
        setPageError((error as Error).message);
      }
    },
    [activeRunId, loadThreads, stream]
  );

  const handleNew = useCallback(() => {
    setActiveRunId(null);
    setMessages([]);
    setAcceptedBodies([]);
    setPageError(null);
    setNotice(null);
    stream.reset();
  }, [stream]);

  const isBusy = state.isStreaming;
  const error = pageError ?? state.error ?? null;

  return (
    <PageShell>
      <PageHeader
        title="Prompt Research"
        tagline="Research a niche with an agent that can search the web, score the idea, and write prompts in your house style."
        icon={<FlaskConical className="h-5 w-5" aria-hidden />}
        actions={
          activeRunId ? (
            <Button
              size="sm"
              variant="secondary"
              icon={<Sparkles className="h-3.5 w-3.5" aria-hidden />}
              disabled={isBusy}
              onClick={handleNew}
            >
              New research
            </Button>
          ) : null
        }
      />

      {error ? (
        <Banner tone="error" onDismiss={() => setPageError(null)}>
          {error}
        </Banner>
      ) : null}
      {notice ? (
        <Banner tone="success" onDismiss={() => setNotice(null)}>
          {notice}
        </Banner>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        {/* ------------------------------- main ------------------------------ */}
        <div className="min-w-0 space-y-4">
          <Panel className="p-3.5">
            <div className="space-y-3">
              <ModeSelector
                modes={settings?.modes ?? []}
                value={mode}
                onChange={setMode}
                disabled={isBusy}
              />
              <ModeDescription mode={activeMode} />
              <ContextWindowBar
                report={state.context}
                fallbackWindow={settings?.context_window ?? 0}
                isLive={isBusy}
              />
              <RunSettingsPanel
                count={count}
                onCountChange={setCount}
                maxPrompts={settings?.max_prompts ?? 60}
                showCount={showCount}
                showValidity={showValidity}
                validityCheck={validityCheck}
                onValidityChange={setValidityCheck}
                disabled={isBusy}
              />
              <HouseStyleEditor
                styleInstruction={houseStyle.draft.styleInstruction}
                onStyleChange={houseStyle.setStyleInstruction}
                houseRules={houseStyle.draft.houseRules}
                onRulesChange={houseStyle.setHouseRules}
                isDirty={houseStyle.isDirty}
                isLoading={houseStyle.isLoading}
                isSaving={houseStyle.isSaving}
                savedAt={houseStyle.savedAt}
                styleIsCustom={houseStyle.styleIsCustom}
                rulesIsCustom={houseStyle.rulesIsCustom}
                onFlush={() => void houseStyle.flush()}
                onReset={() => void houseStyle.reset()}
                onResetStyle={() => void houseStyle.resetStyle()}
                onResetRules={() => void houseStyle.resetRules()}
                error={houseStyle.error}
                disabled={isBusy}
              />
              <PrioritySourcesPanel disabled={isBusy} />
            </div>
          </Panel>

          {messages.length > 0 || isBusy ? (
            <Panel className="p-3.5">
              <ResearchTranscript
                messages={messages}
                steps={state.steps}
                thinking={state.thinking}
                turns={state.turns}
                state={state}
                isLive={isBusy}
              />
            </Panel>
          ) : (
            <Panel className="px-4 py-10 text-center">
              <FlaskConical className="mx-auto h-7 w-7 text-navy-600" aria-hidden />
              <h2 className="mt-3 text-sm font-semibold text-navy-200">
                Start a research thread
              </h2>
              <p className="mx-auto mt-1 max-w-md text-xs leading-relaxed text-navy-400">
                {activeMode?.description ??
                  "Pick a mode above, then describe the niche or idea you want to research."}
              </p>
            </Panel>
          )}

          {state.validity ? (
            <ConfidenceCard validity={state.validity} />
          ) : null}

          {state.followUpActions.length > 0 && !isBusy ? (
            <FollowUpActions actions={state.followUpActions} onSelect={handleFollowUp} />
          ) : null}

          {state.prompts.length > 0 ? (
            <Panel className="p-3.5">
              <PromptResultCard
                prompts={state.prompts}
                acceptedBodies={acceptedBodies}
                isSaving={isSaving}
                summary={state.promptSummary}
                onSave={handleSave}
              />
            </Panel>
          ) : null}

          {state.notices.length > 0 ? (
            <div className="space-y-2">
              {state.notices.map((text, index) => (
                <Banner key={index} tone="warning">
                  {text}
                </Banner>
              ))}
            </div>
          ) : null}

          <Panel className="p-3.5">
            <ResearchComposer
              onSubmit={handleSubmit}
              onStop={stream.stop}
              isStreaming={isBusy}
              activity={isBusy ? activityLine(state) : undefined}
              placeholder={PLACEHOLDERS[mode]}
              suggestions={messages.length === 0 ? SUGGESTIONS[mode] : []}
            />
          </Panel>
        </div>

        {/* ------------------------------ sidebar ---------------------------- */}
        <div className="min-w-0 space-y-4 xl:sticky xl:top-[73px] xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
          <Panel className="flex min-h-0 flex-col p-3.5">
            <ResearchThreadList
              runs={threads}
              activeId={activeRunId}
              onSelect={(runId) => void openRun(runId)}
              onNew={handleNew}
              onDelete={(runId) => void handleDelete(runId)}
              isLoading={isLoadingThreads}
            />
          </Panel>

          <SourcesPanel sources={state.sources} className="px-1" />
        </div>
      </div>
    </PageShell>
  );
}
