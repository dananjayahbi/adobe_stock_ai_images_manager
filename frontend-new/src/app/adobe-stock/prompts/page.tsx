"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import PageSettingsModal from "@/components/prompts/PageSettingsModal";
import type { PromptDetail } from "@/components/prompts/PromptResultsCard";
import ResearchSection from "@/components/prompts/ResearchSection";
import Button from "@/components/ui/Button";
import { useResearchStream } from "@/hooks/useResearchStream";
import {
  acceptResearchPrompts,
  createResearchRun,
  deleteResearchRun,
  fetchResearchRun,
  fetchResearchRuns,
  fetchResearchSettings,
  normalizeMode,
  type FollowUpAction,
  type ResearchMessage,
  type ResearchMode,
  type ResearchRunSummary,
  type ResearchSettings,
} from "@/lib/research";
import { reduceEvents } from "@/lib/researchStream";

/**
 * Prompts: the research workspace. The Prompt Library lives on its own route
 * (`/adobe-stock/prompts/library`) and the editors (system prompts, priority
 * sources, tool budget) behind this page's Settings button.
 *
 * This page owns the top-level state — the vocabulary (`/adobe-stock/settings`), the run
 * list, and the active conversation — while every sub-area lives in its own
 * component. Two flows are worth stating because they are easy to get wrong:
 *
 * * **Start** creates the run with `stream_first: true` (so the opening turn
 *   streams instead of buffering for a minute) and then opens the SSE reader
 *   with *no* `message` — the backend reads the stored turn, so the question is
 *   not appended to the transcript twice.
 * * **Replay** folds the stored run's `events` through the *same* reducer the
 *   live stream uses, so a restored view cannot disagree with the live one.
 */
export default function PromptsPage() {
  const [settings, setSettings] = useState<ResearchSettings | null>(null);
  const [runs, setRuns] = useState<ResearchRunSummary[]>([]);
  const [isLoadingRuns, setLoadingRuns] = useState(true);

  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ResearchMessage[]>([]);

  const [mode, setMode] = useState<ResearchMode>("generate");
  const [count, setCount] = useState(4);
  const [validityCheck, setValidityCheck] = useState(false);

  const [acceptedBodies, setAcceptedBodies] = useState<string[]>([]);
  const [isSaving, setSaving] = useState(false);
  const [isStarting, setStarting] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const stream = useResearchStream();
  const { state } = stream;

  const loadRuns = useCallback(async () => {
    try {
      setRuns(await fetchResearchRuns());
    } catch (err) {
      setPageError(err instanceof Error ? err.message : "Could not load runs.");
    } finally {
      setLoadingRuns(false);
    }
  }, []);

  useEffect(() => {
    void loadRuns();
    fetchResearchSettings()
      .then(setSettings)
      .catch((err) =>
        setPageError(
          err instanceof Error ? err.message : "Could not load research settings."
        )
      );
  }, [loadRuns]);

  // True only while a *live* turn's answer has not yet been folded into the
  // local transcript. Replayed runs (`openRun`) arrive with `finished: true`
  // and their messages already stored — appending there would duplicate them.
  const liveTurnRef = useRef(false);

  // The backend appends the assistant reply to `run.messages` when the turn
  // finishes, but the page's local copy only tracked the user turn — so the
  // answer would vanish from the transcript the moment the live block hid.
  useEffect(() => {
    if (!state.finished || !liveTurnRef.current) return;
    liveTurnRef.current = false;
    const answer = state.answer.trim();
    if (answer) {
      setMessages((current) => [...current, { role: "assistant", content: answer }]);
    }
  }, [state.finished, state.answer]);

  const activeMode = settings?.modes.find((entry) => entry.id === mode);
  const showCount = activeMode?.supports_count ?? false;
  const showValidity = activeMode?.supports_validity ?? false;

  /** Adopt a stored run: load its transcript and replay its events. */
  const openRun = useCallback(
    async (runId: string) => {
      // Abort first: an in-flight stream feeding events while another run's
      // state loads would interleave two transcripts.
      stream.stop();
      setPageError(null);
      setNotice(null);
      try {
        const run = await fetchResearchRun(runId);
        setActiveRunId(run.id);
        setMessages(run.messages ?? []);
        // Legacy `static`/`batch` runs display and behave as `generate`.
        setMode(normalizeMode(run.mode));
        setValidityCheck(Boolean(run.settings?.validity_check));
        setCount(Number(run.settings?.count ?? 4) || 4);
        setAcceptedBodies([]);
        liveTurnRef.current = false;
        // Replay through the same reducer the live stream uses.
        stream.reset({
          ...reduceEvents(run.events ?? []),
          isStreaming: false,
          finished: true,
        });
      } catch (err) {
        setPageError(err instanceof Error ? err.message : "Could not open the run.");
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
      setStarting(true);
      let runId: string;
      try {
        const created = await createResearchRun({
          message,
          mode,
          count: showCount ? count : 1,
          validityCheck: showValidity ? validityCheck : false,
        });
        runId = created.id;
        setActiveRunId(created.id);
        setMessages(created.messages ?? []);
      } catch (err) {
        setPageError(err instanceof Error ? err.message : "Could not start the run.");
        stream.reset();
        return;
      } finally {
        setStarting(false);
      }

      // No `message`: the backend reads the stored turn.
      liveTurnRef.current = true;
      await stream.send({
        runId,
        count: showCount ? count : undefined,
        validityCheck: showValidity ? validityCheck : undefined,
      });
      await loadRuns();
    },
    [
      count,
      loadRuns,
      mode,
      showCount,
      showValidity,
      stream,
      validityCheck,
    ]
  );

  /** Continue the active conversation. */
  const continueRun = useCallback(
    async (message: string) => {
      if (!activeRunId) return;
      setPageError(null);
      setNotice(null);
      // Append the operator's turn immediately so the transcript reads
      // correctly while the reply streams in.
      setMessages((current) => [...current, { role: "user", content: message }]);
      liveTurnRef.current = true;
      await stream.send({
        runId: activeRunId,
        message,
        count: showCount ? count : undefined,
        validityCheck: showValidity ? validityCheck : undefined,
      });
      await loadRuns();
    },
    [activeRunId, count, loadRuns, showCount, showValidity, stream, validityCheck]
  );

  const handleSubmit = useCallback(
    async (message: string) => {
      if (activeRunId) await continueRun(message);
      else await startNew(message);
    },
    [activeRunId, continueRun, startNew]
  );

  /** A validity-gate button: sends the action's own message, verbatim. */
  const handleFollowUp = useCallback(
    (action: FollowUpAction) => {
      void continueRun(action.message);
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
            ? `Added ${outcome.count} prompt${
                outcome.count === 1 ? "" : "s"
              } to the Prompt Library as drafts.`
            : "Those prompts are already in the library."
        );
      } catch (err) {
        setPageError(err instanceof Error ? err.message : "Could not save the prompts.");
      } finally {
        setSaving(false);
      }
    },
    [activeRunId, mode]
  );

  const handleNew = useCallback(() => {
    stream.stop();
    stream.reset();
    liveTurnRef.current = false;
    setActiveRunId(null);
    setMessages([]);
    setAcceptedBodies([]);
    setPageError(null);
    setNotice(null);
  }, [stream]);

  const handleDeleteRun = useCallback(
    async (runId: string) => {
      try {
        await deleteResearchRun(runId);
        if (runId === activeRunId) handleNew();
        await loadRuns();
      } catch (err) {
        setPageError(err instanceof Error ? err.message : "Could not delete the run.");
      }
    },
    [activeRunId, handleNew, loadRuns]
  );

  const isBusy = state.isStreaming || isStarting;
  const error = pageError ?? state.error ?? null;

  return (
    <div className="space-y-8">
      {/* Header: label + title + actions, then the reference's layered rule lines. */}
      <div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="label-caps">Research</p>
            <h1 className="mt-1 font-display text-3xl text-ink-800">Prompts</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/adobe-stock/prompts/library">
              <Button variant="secondary" size="sm" type="button">
                Prompt library
              </Button>
            </Link>
            <Button
              variant="secondary"
              size="sm"
              type="button"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings className="h-3.5 w-3.5" aria-hidden />
              Settings
            </Button>
          </div>
        </div>
        <div className="mt-3 h-px bg-brass-400/50" />
        <div className="mt-[2px] h-px bg-parchment-400" />
      </div>

      {error && (
        <p className="cursor-pointer rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
          {error}
        </p>
      )}
      {notice && (
        <p className="rounded-sm border border-olive-500/60 bg-olive-400/10 px-3 py-2 text-sm text-olive-400" role="status">
          {notice}
        </p>
      )}

      <ResearchSection
        settings={settings}
        runs={runs}
        isLoadingRuns={isLoadingRuns}
        activeRunId={activeRunId}
        messages={messages}
        state={state}
        mode={mode}
        onModeChange={setMode}
        count={count}
        onCountChange={setCount}
        validityCheck={validityCheck}
        onValidityChange={setValidityCheck}
        isBusy={isBusy}
        acceptedBodies={acceptedBodies}
        isSaving={isSaving}
        onFollowUp={handleFollowUp}
        onSavePrompts={(bodies, details) => void handleSave(bodies, details)}
        onSubmit={(message) => void handleSubmit(message)}
        onStop={stream.stop}
        onNew={handleNew}
        onSelectRun={(runId) => void openRun(runId)}
        onDeleteRun={(runId) => void handleDeleteRun(runId)}
      />

      <PageSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
