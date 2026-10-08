"use client";

/**
 * The persistence layer for the house standard and house rules.
 *
 * Owns the draft, the dirty check, and the save — so the editor component stays
 * presentational and `ResearchPage` does not grow another four pieces of state
 * and a debounce.
 *
 * Three decisions worth stating:
 *
 * * **The server response is the source of truth after a save.** It strips
 *   whitespace and turns a blank value back into the shipped default, so echoing
 *   the submitted text into state would leave the box showing something runs
 *   will not use.
 * * **A run in flight does not block saving.** The saved text applies to the
 *   *next* run; blocking would be surprising. The editor is disabled while
 *   streaming so the operator is not typing into a box the next turn will
 *   silently not use — the page passes `disabled` for that.
 * * **Draft text lives in a ref as well as in state.** The debounce callback and
 *   the unmount flush both need the current text without being rebuilt on every
 *   keystroke, which would restart the timer each time and defeat the debounce.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchHouseStyle,
  saveHouseStyle,
  type HouseStyle,
} from "@/lib/houseStyle";

/** Delay before a keystroke settles into a request. */
const SAVE_DEBOUNCE_MS = 900;

export interface UseHouseStyleResult {
  /** What the operator currently sees in the boxes. */
  draft: { styleInstruction: string; houseRules: string };
  /** True when the draft differs from what is stored. */
  isDirty: boolean;
  /** True when either field has been customised away from the shipped default. */
  hasCustom: boolean;
  /** Per-field "the operator wrote this", as the server reports it. */
  styleIsCustom: boolean;
  rulesIsCustom: boolean;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  /** Set once a save succeeds, for a brief confirmation. */
  savedAt: number | null;
  setStyleInstruction: (value: string) => void;
  setHouseRules: (value: string) => void;
  /** Force the pending save to happen now (blur, run start, unmount). */
  flush: () => Promise<void>;
  /**
   * The style instruction as it stands *right now*.
   *
   * A ref-backed accessor rather than reading `draft.styleInstruction`, because
   * the caller that needs it (`startNew`) must flush first and then send — and a
   * value captured in a `useCallback` closure would be the pre-flush text. The
   * server strips whitespace, so the pre-flush value can differ from what it
   * stores, and the run would then carry a style the operator never sees saved.
   */
  currentStyle: () => string;
  /** Restore both fields to the shipped defaults. */
  reset: () => Promise<void>;
  /**
   * Restore one field only.
   *
   * Separate from `reset` because each textarea has its own Reset button, and a
   * shared handler there would silently discard the *other* field's edits — the
   * kind of surprise that makes an operator stop trusting the save button.
   */
  resetStyle: () => Promise<void>;
  resetRules: () => Promise<void>;
  /** Called when a run starts, so a pending save cannot lag behind the run. */
  markRunStarted: () => void;
}

export function useHouseStyle(): UseHouseStyleResult {
  const [stored, setStored] = useState<HouseStyle | null>(null);
  const [styleDraft, setStyleDraft] = useState("");
  const [rulesDraft, setRulesDraft] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Mirrors the drafts so the timer callback reads the current text without
  // being re-created on every keystroke (which would reset the debounce).
  const draftRef = useRef({ styleInstruction: "", houseRules: "" });
  /** The last text confirmed stored, for the dirty check inside the callback. */
  const storedRef = useRef<HouseStyle | null>(null);

  const applyStored = useCallback((next: HouseStyle) => {
    storedRef.current = next;
    setStored(next);
    const draft = {
      styleInstruction: next.style_instruction,
      houseRules: next.house_rules,
    };
    draftRef.current = draft;
    setStyleDraft(draft.styleInstruction);
    setRulesDraft(draft.houseRules);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const loaded = await fetchHouseStyle();
        if (!cancelled) applyStored(loaded);
      } catch (problem) {
        if (!cancelled) setError((problem as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyStored]);

  const isDirty =
    stored !== null &&
    (styleDraft !== stored.style_instruction || rulesDraft !== stored.house_rules);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const persist = useCallback(async () => {
    const current = storedRef.current;
    if (current === null) return;
    const draft = draftRef.current;
    if (
      draft.styleInstruction === current.style_instruction &&
      draft.houseRules === current.house_rules
    ) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveHouseStyle({
        style_instruction: draft.styleInstruction,
        house_rules: draft.houseRules,
      });
      // Only adopt the server's answer if the operator has not typed again
      // while the request was in flight — otherwise their newer keystrokes are
      // thrown away by a response describing the older text.
      if (
        draftRef.current.styleInstruction === draft.styleInstruction &&
        draftRef.current.houseRules === draft.houseRules
      ) {
        applyStored(saved);
        setSavedAt(Date.now());
      } else {
        storedRef.current = saved;
        setStored(saved);
      }
    } catch (problem) {
      setError((problem as Error).message);
    } finally {
      setSaving(false);
    }
  }, [applyStored]);

  const scheduleSave = useCallback(() => {
    clearTimer();
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      void persist();
    }, SAVE_DEBOUNCE_MS);
  }, [clearTimer, persist]);

  const setStyleInstruction = useCallback(
    (value: string) => {
      draftRef.current = { ...draftRef.current, styleInstruction: value };
      setStyleDraft(value);
      scheduleSave();
    },
    [scheduleSave]
  );

  const setHouseRules = useCallback(
    (value: string) => {
      draftRef.current = { ...draftRef.current, houseRules: value };
      setRulesDraft(value);
      scheduleSave();
    },
    [scheduleSave]
  );

  /**
   * Restore the named fields to the shipped defaults.
   *
   * Implemented as "blank the draft, then persist" rather than as a separate
   * reset request, because the server's contract already says a blank field means
   * "use the default" — and it returns the effective value, so the box refills
   * with the real default text rather than sitting empty. A second code path to
   * the same store would be a second thing that can disagree with the first.
   *
   * Fields not named are left exactly as they are, including unsaved edits.
   */
  const applyReset = useCallback(
    async (fields: { style?: boolean; rules?: boolean }) => {
      clearTimer();
      if (fields.style) {
        draftRef.current = { ...draftRef.current, styleInstruction: "" };
        setStyleDraft("");
      }
      if (fields.rules) {
        draftRef.current = { ...draftRef.current, houseRules: "" };
        setRulesDraft("");
      }
      await persist();
    },
    [clearTimer, persist]
  );

  const flush = useCallback(async () => {
    clearTimer();
    await persist();
  }, [clearTimer, persist]);

  const reset = useCallback(async () => {
    await applyReset({ style: true, rules: true });
  }, [applyReset]);

  const resetStyle = useCallback(async () => {
    await applyReset({ style: true });
  }, [applyReset]);

  const resetRules = useCallback(async () => {
    await applyReset({ rules: true });
  }, [applyReset]);

  /**
   * Abort an in-flight save's effect on the state when a run starts.
   *
   * Not a save and not a discard — just stops the confirmation tick and clears a
   * stale error, so a run does not appear to have been preceded by a save it
   * never waited for.
   */
  const markRunStarted = useCallback(() => {
    clearTimer();
    setSavedAt(null);
    setError(null);
  }, [clearTimer]);

  const currentStyle = useCallback(() => draftRef.current.styleInstruction, []);

  // Flush on unmount so navigating away does not discard the last few
  // keystrokes that had not yet reached the debounce timer.
  useEffect(() => () => void flush(), [flush]);

  return {
    draft: { styleInstruction: styleDraft, houseRules: rulesDraft },
    isDirty,
    hasCustom: Boolean(stored?.style_is_custom || stored?.rules_is_custom),
    // Read from the server's flags, not inferred by comparing the draft against a
    // default fetched elsewhere: the page also fetches `research/settings`, which
    // serves the *saved* value under the key `default_style_instruction`, so a
    // client-side compare there would always report "custom".
    styleIsCustom: Boolean(stored?.style_is_custom),
    rulesIsCustom: Boolean(stored?.rules_is_custom),
    isLoading,
    isSaving,
    error,
    savedAt,
    setStyleInstruction,
    setHouseRules,
    flush,
    reset,
    resetStyle,
    resetRules,
    markRunStarted,
    currentStyle,
  };
}