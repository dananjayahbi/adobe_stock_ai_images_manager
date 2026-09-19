"use client";

import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";

/**
 * Stage 5 — Compatibility Check.
 *
 * The full acceptance algorithm, gated at the 80% threshold. This is the page
 * where the operator finds out whether an image is actually sellable, so the
 * Compatible/Incompatible buckets are the primary readout.
 */
export default function CompatibilityPage() {
  return (
    <RunnableStagePage
      stageKey="compatibility"
      emptyDescription="Push refined images here, then run the acceptance check to score them."
    />
  );
}
