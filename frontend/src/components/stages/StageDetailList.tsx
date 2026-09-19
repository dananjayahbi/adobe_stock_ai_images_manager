"use client";

import { ScanText, Maximize2, SlidersHorizontal, CheckCircle2 } from "lucide-react";

import type { ImageRecord } from "@/lib/api";

interface StageDetailListProps {
  record: ImageRecord;
}

/**
 * Renders the per-stage findings recorded on a record.
 *
 * Each stage stores a structured detail blob (OCR words, upscale backend,
 * refine pass log, compatibility verdict). Surfacing them chronologically lets
 * the operator trace exactly what the pipeline did to an image.
 */
export default function StageDetailList({ record }: StageDetailListProps) {
  const details = record.stage_details ?? {};
  const sections: React.ReactNode[] = [];

  if (details.ocr) {
    const ocr = details.ocr;
    sections.push(
      <Section
        key="ocr"
        icon={<ScanText className="h-3.5 w-3.5" />}
        title="OCR scan"
        tone={ocr.blocked ? "bad" : "good"}
      >
        <Row label="Result" value={ocr.classification.replace("_", " ")} />
        <Row label="Words" value={String(ocr.word_count)} />
        <Row label="Mean confidence" value={`${ocr.mean_confidence.toFixed(1)}%`} />
        {ocr.reason && <Note>{ocr.reason}</Note>}
        {ocr.text && (
          <pre className="mt-1.5 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-zinc-950/60 p-2 text-[11px] text-zinc-400">
            {ocr.text}
          </pre>
        )}
      </Section>
    );
  }

  if (details.upscale) {
    const up = details.upscale;
    sections.push(
      <Section
        key="upscale"
        icon={<Maximize2 className="h-3.5 w-3.5" />}
        title="Upscale"
        tone={up.success ? "good" : "warn"}
      >
        <Row label="Backend" value={up.backend} />
        <Row label="Scale" value={`${up.scale.toFixed(2)}×`} />
        <Row
          label="Resolution"
          value={`${up.source_megapixels.toFixed(1)} MP → ${up.output_megapixels.toFixed(1)} MP`}
        />
        {up.reason && <Note>{up.reason}</Note>}
      </Section>
    );
  }

  if (details.refine) {
    const refine = details.refine;
    sections.push(
      <Section
        key="refine"
        icon={<SlidersHorizontal className="h-3.5 w-3.5" />}
        title="Refinement"
        tone={refine.success ? "good" : "warn"}
      >
        <Row
          label="Score"
          value={`${(refine.initial_score * 100).toFixed(1)}% → ${(refine.final_score * 100).toFixed(1)}%`}
        />
        <Row label="Passes" value={String(refine.passes)} />
        {refine.reason && <Note>{refine.reason}</Note>}

        {refine.history.length > 0 && (
          <ol className="mt-2 space-y-1.5">
            {refine.history.map((entry) => (
              <li
                key={entry.pass}
                className="rounded border border-zinc-800/70 bg-zinc-950/40 px-2 py-1.5 text-[11px]"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-zinc-400">
                    Pass {entry.pass}
                  </span>
                  <span className="tabular-nums text-zinc-300">
                    {(entry.score * 100).toFixed(1)}%
                  </span>
                </div>
                {entry.note && <p className="text-zinc-500">{entry.note}</p>}
                {entry.operations?.map((operation, index) => (
                  <p key={index} className="text-zinc-500">
                    · {operation.operation} ({operation.strength.toFixed(2)})
                  </p>
                ))}
                {entry.unaddressable && entry.unaddressable.length > 0 && (
                  <p className="text-amber-400/90">
                    Needs manual review: {entry.unaddressable.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ol>
        )}
      </Section>
    );
  }

  if (details.compatibility) {
    const compat = details.compatibility;
    sections.push(
      <Section
        key="compatibility"
        icon={<CheckCircle2 className="h-3.5 w-3.5" />}
        title="Compatibility verdict"
        tone={compat.passed ? "good" : "bad"}
      >
        <Row label="Score" value={`${compat.confidence_percent.toFixed(1)}%`} />
        <Row label="Threshold" value={`${(compat.threshold * 100).toFixed(0)}%`} />
        <Note>{compat.summary}</Note>
      </Section>
    );
  }

  if (sections.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-zinc-800 px-4 py-4 text-center text-xs text-zinc-500">
        No stage findings recorded yet.
      </p>
    );
  }

  return <div className="space-y-3">{sections}</div>;
}

function Section({
  icon,
  title,
  tone,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  tone: "good" | "warn" | "bad";
  children: React.ReactNode;
}) {
  const toneStyles = {
    good: "border-emerald-500/30 bg-emerald-500/5",
    warn: "border-amber-500/30 bg-amber-500/5",
    bad: "border-red-500/30 bg-red-500/5",
  }[tone];

  return (
    <section className={`rounded-lg border px-3 py-2.5 ${toneStyles}`}>
      <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-zinc-400">
        {icon}
        {title}
      </h4>
      <div className="space-y-0.5 text-xs">{children}</div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-zinc-500">{label}</span>
      <span className="truncate font-medium text-zinc-300" title={value}>
        {value}
      </span>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-zinc-400">{children}</p>;
}
