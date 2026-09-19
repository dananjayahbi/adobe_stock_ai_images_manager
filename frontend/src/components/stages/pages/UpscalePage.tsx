"use client";

import { useEffect, useState } from "react";

import RunnableStagePage from "@/components/stages/pages/RunnableStagePage";
import UpscaleOptionsPanel from "@/components/stages/UpscaleOptionsPanel";
import {
  FALLBACK_UPSCALE_OPTIONS,
  fetchUpscaleDefaults,
  type UpscaleOptions,
} from "@/lib/upscale";

/**
 * Stage 3 — Upscale.
 *
 * The only stage whose run depends on operator choices, so its options panel is
 * lifted to page level (it used to be squeezed into a narrow sidebar slot) and
 * the chosen configuration is passed straight to the run.
 */
export default function UpscalePage() {
  const [options, setOptions] = useState<UpscaleOptions>(FALLBACK_UPSCALE_OPTIONS);

  // Seed from the server so the panel and the batch agree on defaults even if
  // the operator never opens the panel.
  useEffect(() => {
    void fetchUpscaleDefaults()
      .then(setOptions)
      .catch(() => {
        /* The panel fetches the catalog itself and will surface the failure. */
      });
  }, []);

  return (
    <RunnableStagePage
      stageKey="upscale"
      runOptions={{ upscale: options }}
      emptyDescription="Push cleared images here from the OCR Detector, choose your upscale settings, then run the batch."
      panels={<UpscaleOptionsPanel value={options} onChange={setOptions} />}
    />
  );
}
