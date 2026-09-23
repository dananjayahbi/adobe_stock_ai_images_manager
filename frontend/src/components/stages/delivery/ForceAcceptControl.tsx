"use client";

import { ShieldCheck, ShieldOff } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { forceAccept } from "@/lib/delivery";
import type { ImageRecord } from "@/lib/api";

export interface ForceAcceptControlProps {
  /** Records currently selected on the page. */
  records: ImageRecord[];
  onError: (message: string | null) => void;
  onNotice: (message: string | null) => void;
  onAccepted: () => Promise<void> | void;
  disabled?: boolean;
}

/**
 * Manual override of the acceptance gate.
 *
 * The acceptance score is a *ranking* signal — Adobe publishes no numeric
 * threshold and reviewer variance exceeds any threshold's resolution — so there
 * are real cases where the operator's judgement is better than the scorer's.
 * Without this control those images were dead ends.
 *
 * Two design points that matter:
 *
 * * **The reason is captured, not optional-by-accident.** An override that leaves
 *   no trace is indistinguishable from a bug in the gate, so the operator is
 *   asked *why* and the answer is stored with the score that was overridden.
 * * **The score is not rewritten.** The record keeps its honest measurement and
 *   shows the override separately. Silently editing the number to look like a
 *   pass would destroy the signal the whole pipeline exists to produce.
 */
export function ForceAcceptControl({
  records,
  onError,
  onNotice,
  onAccepted,
  disabled = false,
}: ForceAcceptControlProps) {
  const [reason, setReason] = useState("");
  const [isBusy, setBusy] = useState(false);
  const [showReason, setShowReason] = useState(false);

  const flagged = records.filter(
    (record) => record.stage === "INCOMPATIBLE" || record.stage === "COLLECTED"
  );
  const count = records.length;

  async function handleForce() {
    if (count === 0) return;
    setBusy(true);
    onError(null);
    try {
      const result = await forceAccept(
        records.map((record) => record.id),
        reason
      );
      await onAccepted();

      if (result.refused > 0) {
        const refusal = result.items.find((item) => !item.accepted);
        onError(
          `${result.accepted} accepted, ${result.refused} refused.${
            refusal ? ` ${refusal.reason}` : ""
          }`
        );
      } else {
        onNotice(
          `${result.accepted} image(s) force-accepted. The original score and issues are kept for the record.`
        );
        setReason("");
        setShowReason(false);
      }
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Could not force-accept the images."
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {showReason ? (
        <input
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          placeholder="Why is this acceptable? (stored with the override)"
          aria-label="Reason for force-accepting"
          className={cn(
            "w-64 rounded-lg border border-amber-500/40 bg-navy-900/60 px-2.5 py-1.5",
            "text-[11px] text-navy-50 placeholder:text-navy-500",
            "focus:border-amber-400/70 focus:outline-none focus:ring-1 focus:ring-amber-400/40"
          )}
        />
      ) : null}

      <Button
        size="sm"
        variant={showReason ? "primary" : "secondary"}
        disabled={disabled || isBusy || count === 0}
        isLoading={isBusy}
        onClick={() => {
          if (!showReason) {
            setShowReason(true);
            return;
          }
          void handleForce();
        }}
        icon={
          isBusy ? undefined : showReason ? (
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <ShieldOff className="h-3.5 w-3.5" aria-hidden />
          )
        }
        title={
          count === 0
            ? "Select images to force-accept"
            : `Force-accept ${count} image(s) past the acceptance gate`
        }
      >
        {showReason
          ? `Confirm accept (${count})`
          : flagged.length > 0
            ? `Force accept (${flagged.length})`
            : `Force accept (${count})`}
      </Button>

      {showReason ? (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setShowReason(false);
            setReason("");
          }}
        >
          Cancel
        </Button>
      ) : null}
    </div>
  );
}

export default ForceAcceptControl;
