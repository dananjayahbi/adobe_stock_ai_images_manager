"use client";

import { useCallback, useState } from "react";

/**
 * Pending-destructive-action state for a confirmation modal.
 *
 * Every delete in the app is irreversible — the backend unlinks the inbox
 * original, the thumbnail, and every staged copy — so each one has to be
 * confirmed. Rather than repeat the open/busy/error/close bookkeeping in every
 * page, the pages own only the *action* and this hook owns the dialog state.
 *
 * `run` deliberately keeps the dialog open when the action rejects: a failure
 * belongs next to the button that caused it, not in a toast the operator may
 * miss.
 */
export interface ConfirmAction<T> {
  /** The payload the pending action will operate on, or null when idle. */
  target: T | null;
  isOpen: boolean;
  isBusy: boolean;
  error: string | null;
  /** Open the dialog for `target`. */
  request: (target: T) => void;
  /** Close without acting. */
  cancel: () => void;
  /** Run `action` against the pending target, then close on success. */
  run: (action: (target: T) => Promise<void>) => Promise<void>;
}

export function useConfirmAction<T>(): ConfirmAction<T> {
  const [target, setTarget] = useState<T | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const request = useCallback((next: T) => {
    setTarget(next);
    setError(null);
  }, []);

  const cancel = useCallback(() => {
    if (isBusy) return;
    setTarget(null);
    setError(null);
  }, [isBusy]);

  const run = useCallback(
    async (action: (target: T) => Promise<void>) => {
      if (target === null) return;
      setIsBusy(true);
      setError(null);
      try {
        await action(target);
        setTarget(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "The action failed.");
      } finally {
        setIsBusy(false);
      }
    },
    [target]
  );

  return {
    target,
    isOpen: target !== null,
    isBusy,
    error,
    request,
    cancel,
    run,
  };
}

/**
 * Pluralised noun phrase for a confirmation message.
 *
 * Kept here rather than inlined so every delete dialog words its subject the
 * same way ("1 image" / "3 images").
 */
export function pluralise(count: number, singular: string, plural?: string): string {
  return count === 1 ? `1 ${singular}` : `${count} ${plural ?? `${singular}s`}`;
}
