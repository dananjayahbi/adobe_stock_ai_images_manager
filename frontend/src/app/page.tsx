"use client";

import { AlertCircle, Loader2, Radio } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import Dropzone from "@/components/Dropzone";
import ImageGrid from "@/components/ImageGrid";
import InspectionModal from "@/components/InspectionModal";
import StatsBar from "@/components/StatsBar";
import {
  approveBatch,
  approveRecord,
  fetchRecords,
  type ApproveOverrides,
  type ImageRecord,
} from "@/lib/api";

const POLL_INTERVAL_MS = 3000;

export default function Dashboard() {
  const [records, setRecords] = useState<ImageRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isApproving, setIsApproving] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState<ImageRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const inFlight = useRef(false);

  const loadRecords = useCallback(async (showSpinner = false) => {
    if (inFlight.current) return;
    inFlight.current = true;
    if (showSpinner) setIsLoading(true);
    try {
      const response = await fetchRecords({ limit: 500 });
      setRecords(response.items);
      setLastUpdated(new Date());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load records.");
    } finally {
      inFlight.current = false;
      if (showSpinner) setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecords(true);
    const interval = setInterval(() => void loadRecords(), POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [loadRecords]);

  useEffect(() => {
    if (!selectedRecord) return;
    const refreshed = records.find((r) => r.id === selectedRecord.id);
    if (refreshed && refreshed !== selectedRecord) setSelectedRecord(refreshed);
  }, [records, selectedRecord]);

  const handleApprove = useCallback(
    async (id: string, overrides?: ApproveOverrides) => {
      setIsApproving(true);
      try {
        await approveRecord(id, overrides);
        await loadRecords();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Approval failed.");
      } finally {
        setIsApproving(false);
      }
    },
    [loadRecords]
  );

  const handleBatchApprove = useCallback(async () => {
    const passedIds = records
      .filter((record) => record.status === "PASSED")
      .map((record) => record.id);
    if (passedIds.length === 0) return;

    setIsApproving(true);
    try {
      await approveBatch(passedIds);
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Batch approval failed.");
    } finally {
      setIsApproving(false);
    }
  }, [records, loadRecords]);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-8 text-zinc-100">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              Adobe Stock AI Image Studio
            </h1>
            <p className="text-sm text-zinc-500">
              Deterministic QC → semantic audit → human approval → tagged assets.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500">
            <Radio className="h-3.5 w-3.5 text-emerald-400" />
            {lastUpdated
              ? `Live · updated ${lastUpdated.toLocaleTimeString()}`
              : "Connecting…"}
          </span>
        </header>

        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <StatsBar
          records={records}
          onBatchApprove={handleBatchApprove}
          isApproving={isApproving}
        />

        <Dropzone onUploadComplete={() => void loadRecords(true)} />

        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Pipeline Queue
          </h2>
          {isLoading && records.length === 0 ? (
            <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-800 py-12 text-zinc-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading records…
            </div>
          ) : (
            <ImageGrid
              records={records}
              onInspect={setSelectedRecord}
              onApprove={(id) => void handleApprove(id)}
              isLoading={isLoading}
            />
          )}
        </section>
      </div>

      <InspectionModal
        record={selectedRecord}
        isOpen={selectedRecord !== null}
        onClose={() => setSelectedRecord(null)}
        onApprove={(id, overrides) => void handleApprove(id, overrides)}
        isApproving={isApproving}
      />
    </main>
  );
}
