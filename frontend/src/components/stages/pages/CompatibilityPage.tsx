"use client";

import { useState } from "react";

import ForceAcceptControl from "@/components/stages/delivery/ForceAcceptControl";
import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";
import type { ImageRecord } from "@/lib/api";

/**
 * Stage 5 — Compatibility Check.
 *
 * The full acceptance algorithm, gated at the 80% threshold. This is the page
 * where the operator finds out whether an image is actually sellable, so the
 * Compatible/Incompatible buckets are the primary readout.
 *
 * It is also where the **manual override** belongs: a below-threshold record
 * lands here, and the operator's judgement about whether it is genuinely usable
 * is formed while looking at the score and its issues. Making them go to a later
 * page to act on that judgement would separate the decision from the evidence.
 */
export default function CompatibilityPage() {
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <RunnableStagePage
      stageKey="compatibility"
      emptyDescription="Push refined images here, then run the acceptance check to score them."
      error={error}
      notice={notice}
      onClearError={() => setError(null)}
      onClearNotice={() => setNotice(null)}
      extraActions={(selected: ImageRecord[]) =>
        // Only offered when the selection actually contains something the gate
        // flagged, so the button never promises a no-op.
        selected.some(
          (record) =>
            record.stage === "INCOMPATIBLE" || record.stage === "COLLECTED"
        ) ? (
          <ForceAcceptControl
            records={selected}
            onError={setError}
            onNotice={setNotice}
            // Nothing to refresh explicitly: the page polls, and the override
            // only changes the stage the poll already reads.
            onAccepted={() => undefined}
          />
        ) : null
      }
    />
  );
}
