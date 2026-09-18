"use client";

import { CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { useMemo } from "react";

import type { ImageRecord, ImageStatus } from "@/lib/api";

interface StatsBarProps {
  records: ImageRecord[];
  onBatchApprove?: () => void;
  isApproving?: boolean;
}

const BADGE_STYLES: Record<ImageStatus, string> = {
  PENDING: "bg-zinc-700/40 text-zinc-300 border-zinc-600/50",
  AUDITING: "bg-zinc-600/40 text-zinc-200 border-zinc-500/50",
  PASSED: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  FLAGGED: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  APPROVED: "bg-violet-500/15 text-violet-300 border-violet-500/40",
  READY: "bg-blue-500/15 text-blue-300 border-blue-500/40",
};

export default function StatsBar({
  records,
  onBatchApprove,
  isApproving = false,
}: StatsBarProps) {
  const counts = useMemo(() => {
    const base: Record<ImageStatus, number> = {
      PENDING: 0,
      AUDITING: 0,
      PASSED: 0,
      FLAGGED: 0,
      APPROVED: 0,
      READY: 0,
    };
    for (const record of records) {
      if (base[record.status] !== undefined) base[record.status] += 1;
    }
    return base;
  }, [records]);

  const total = records.length;
  const passedCount = counts.PASSED;

  const metrics: { key: ImageStatus; label: string }[] = [
    { key: "PENDING", label: "Pending" },
    { key: "AUDITING", label: "Auditing" },
    { key: "PASSED", label: "Passed" },
    { key: "FLAGGED", label: "Flagged" },
    { key: "READY", label: "Ready" },
  ];

  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-4 py-2">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Total</p>
          <p className="text-xl font-semibold text-zinc-100">{total}</p>
        </div>

        {metrics.map(({ key, label }) => (
          <div
            key={key}
            className={`rounded-lg border px-4 py-2 ${BADGE_STYLES[key]}`}
          >
            <p className="text-xs uppercase tracking-wide opacity-80">{label}</p>
            <p className="text-xl font-semibold">{counts[key]}</p>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onBatchApprove}
        disabled={passedCount === 0 || isApproving || !onBatchApprove}
        className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400"
      >
        {isApproving ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : passedCount > 0 ? (
          <Sparkles className="h-4 w-4" />
        ) : (
          <CheckCircle2 className="h-4 w-4" />
        )}
        {isApproving
          ? "Approving…"
          : `Batch Approve Passed (${passedCount})`}
      </button>
    </div>
  );
}
