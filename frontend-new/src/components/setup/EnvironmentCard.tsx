"use client";

import { useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import type { Environment, ProbeResult } from "@/lib/setup";

interface EnvironmentCardProps {
  environment: Environment;
  /** Latest probe result (page state, not re-fetched here). */
  probe: ProbeResult | null;
  probing: boolean;
  onProbe: () => void;
}

interface Row {
  label: string;
  value: string | null;
}

/**
 * Human-readable timestamp, falling back to the raw string when `ran_at`
 * is not something `Date` can parse (contract says "string", not ISO).
 */
function formatRanAt(ranAt: string): string {
  const parsed = new Date(ranAt);
  return Number.isNaN(parsed.getTime()) ? ranAt : parsed.toLocaleString();
}

/**
 * The server's Python environment: interpreter, key packages, the ViTMatte
 * readiness chip, and a manual verification probe whose raw output collapses
 * behind a toggle (reference-style: the summary is the headline, the
 * monospace transcript is on demand).
 */
export default function EnvironmentCard({
  environment,
  probe,
  probing,
  onProbe,
}: EnvironmentCardProps) {
  const [outputOpen, setOutputOpen] = useState(false);

  const rows: Row[] = [
    { label: "Python", value: environment.python },
    { label: "Venv", value: environment.venv },
    { label: "PyTorch", value: environment.torch },
    { label: "Transformers", value: environment.transformers },
    { label: "Tokenizers", value: environment.tokenizers },
    { label: "ONNX Runtime (GPU)", value: environment.onnxruntime_gpu },
    { label: "OpenCV", value: environment.opencv },
  ];

  return (
    <Card
      header={
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="label-caps">Environment</p>
            <h2 className="mt-0.5 font-display text-xl text-ink-800">
              Python &amp; runtime
            </h2>
          </div>
          <Badge tone={environment.vitmatte_ready ? "success" : "neutral"}>
            {environment.vitmatte_ready ? "ViTMatte ready" : "ViTMatte not ready"}
          </Badge>
        </div>
      }
    >
      <div className="space-y-4">
        <dl className="divide-y divide-parchment-400/70">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5"
            >
              <dt className="label-caps">{row.label}</dt>
              <dd className="min-w-0 break-all font-mono text-xs text-ink-600">
                {row.value ?? <span className="text-ink-400">not found</span>}
              </dd>
            </div>
          ))}
        </dl>

        <div className="divider-dashed pt-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="label-caps">Verification</p>
              <p className="mt-0.5 text-sm text-ink-400">
                {probe
                  ? probe.ok
                    ? "Last run passed."
                    : "Last run failed — see the output."
                  : "Not run yet."}
              </p>
            </div>
            <Button
              variant="secondary"
              size="sm"
              type="button"
              loading={probing}
              onClick={onProbe}
            >
              Run verification
            </Button>
          </div>

          {probe && (
            <div className="mt-3">
              <button
                type="button"
                onClick={() => setOutputOpen((open) => !open)}
                aria-expanded={outputOpen}
                className="flex w-full items-center justify-between gap-2 rounded-sm border border-parchment-400/70 px-3 py-1.5 text-left transition-colors hover:bg-parchment-200"
              >
                <span className="flex items-center gap-2">
                  <Badge tone={probe.ok ? "success" : "danger"}>
                    {probe.ok ? "Passed" : "Failed"}
                  </Badge>
                  <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
                    ran {formatRanAt(probe.ran_at)}
                  </span>
                </span>
                <span className="font-stamp text-xs text-ink-400">
                  {outputOpen ? "▾ Hide output" : "▸ Show output"}
                </span>
              </button>
              {outputOpen && (
                <pre className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-sm border border-parchment-400/70 bg-ink-900/40 px-3 py-2 font-mono text-xs leading-relaxed text-ink-600">
                  {probe.output || "(no output)"}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}
