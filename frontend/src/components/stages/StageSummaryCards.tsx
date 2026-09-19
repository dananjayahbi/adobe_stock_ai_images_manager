"use client";

import { Ban, CheckCircle2, Gauge, Layers } from "lucide-react";

import { formatScore, type StageSummary } from "@/lib/stages";

interface StageSummaryCardsProps {
  summary: StageSummary | null;
}

/**
 * Headline pipeline metrics.
 *
 * Shows the three numbers an operator actually acts on: how much is in flight,
 * how much is ready to upload, and how much has been rejected outright.
 */
export default function StageSummaryCards({ summary }: StageSummaryCardsProps) {
  const cards = [
    {
      key: "total",
      label: "In pipeline",
      value: summary?.total ?? 0,
      icon: Layers,
      tone: "text-zinc-200",
    },
    {
      key: "ready",
      label: "Ready to upload",
      value: summary?.ready ?? 0,
      icon: CheckCircle2,
      tone: "text-emerald-300",
    },
    {
      key: "rejected",
      label: "Rejected (text)",
      value: summary?.rejected ?? 0,
      icon: Ban,
      tone: "text-red-300",
    },
    {
      key: "incompatible",
      label: "Below threshold",
      value: summary?.incompatible ?? 0,
      icon: Gauge,
      tone: "text-amber-300",
    },
    {
      key: "average",
      label: "Average score",
      value: formatScore(summary?.average_score ?? null),
      icon: Gauge,
      tone: "text-sky-300",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map(({ key, label, value, icon: Icon, tone }) => (
        <div
          key={key}
          className="rounded-xl border border-zinc-800 bg-zinc-900/50 px-3.5 py-2.5"
        >
          <div className="flex items-center gap-1.5">
            <Icon className={`h-3.5 w-3.5 ${tone}`} />
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {label}
            </p>
          </div>
          <p className={`mt-0.5 text-xl font-semibold tabular-nums ${tone}`}>
            {value}
          </p>
        </div>
      ))}
    </div>
  );
}
