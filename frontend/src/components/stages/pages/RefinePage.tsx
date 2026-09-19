"use client";

import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";

/**
 * Stage 4 — Image Refiner.
 *
 * Corrective passes driven by the last acceptance report. The operator selects
 * the images that fell short, refines them, and pushes the improved copies on.
 */
export default function RefinePage() {
  return (
    <RunnableStagePage
      stageKey="refine"
      emptyDescription="Push upscaled images here, then run the refiner on the ones that need corrective passes."
    />
  );
}
