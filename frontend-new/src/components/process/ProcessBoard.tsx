"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useBatchList } from "@/hooks/useBatchList";
import {
  isBatchActive,
  isBatchFinished,
  queuePositions,
} from "@/components/process/batchStatus";
import ProcessSection from "./ProcessSection";
import ProcessRow from "./ProcessRow";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";

/**
 * The Processes ledger: every batch grouped into Active (running → queued in
 * queue order), Drafts, and Finished (most recent first) — the client-side
 * contract order. Rows link back to the batch page, and the dual-cadence
 * hook keeps the queue live without polling hard while idle.
 */
export default function ProcessBoard() {
  const { batches, loading, error, refresh } = useBatchList();
  const router = useRouter();

  const positions = useMemo(() => queuePositions(batches), [batches]);

  const { active, drafts, finished } = useMemo(() => {
    const active = batches.filter((batch) => isBatchActive(batch.status));
    const drafts = batches.filter((batch) => batch.status === "draft");
    const finished = batches.filter((batch) => isBatchFinished(batch.status));

    // Contract order: running first, then queued by queued_at asc. Ties among
    // running (the server runs serially, so this is rare) break recent-first.
    active.sort((a, b) => {
      if (a.status !== b.status) return a.status === "running" ? -1 : 1;
      if (a.status === "running") return b.updated_at.localeCompare(a.updated_at);
      return (a.queued_at ?? "~").localeCompare(b.queued_at ?? "~");
    });
    // Drafts and terminal states: most recently touched first.
    drafts.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    finished.sort((a, b) => b.updated_at.localeCompare(a.updated_at));

    return { active, drafts, finished };
  }, [batches]);

  const open = useCallback(
    (id: string) => {
      void router.push(`/adobe-stock/batch/${id}`);
    },
    [router]
  );

  if (loading && batches.length === 0 && !error) {
    return (
      <div className="space-y-3" aria-busy="true">
        <div className="frame-card h-24 animate-pulse bg-parchment-200" />
        <div className="frame-card h-24 animate-pulse bg-parchment-200" />
        <div className="frame-card h-24 animate-pulse bg-parchment-200" />
      </div>
    );
  }

  if (error && batches.length === 0) {
    return (
      <div className="frame-card px-5 py-4" role="alert">
        <p className="text-sm text-oxblood-400">{error}</p>
        <Button
          variant="secondary"
          size="sm"
          className="mt-3"
          onClick={() => void refresh()}
        >
          Try again
        </Button>
      </div>
    );
  }

  if (batches.length === 0) {
    return (
      <EmptyState
        glyph="№"
        title="No batches yet"
        body="Create a batch from Home — it will appear here while it runs and stay in the ledger afterwards."
        action={
          <Link href="/adobe-stock">
            <Button size="lg">New batch</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="space-y-8">
      {error && (
        <p
          className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
          role="alert"
        >
          {error}
        </p>
      )}

      <ProcessSection
        id="active"
        label="Active"
        caption="running or queued"
        emptyText="Nothing in flight — the queue is clear."
      >
        {active.map((batch) => (
          <ProcessRow
            key={batch.id}
            batch={batch}
            position={
              batch.status === "queued" ? positions.get(batch.id) : undefined
            }
            onOpen={open}
          />
        ))}
      </ProcessSection>

      <ProcessSection
        id="drafts"
        label="Drafts"
        caption="not yet run"
        emptyText="No drafts waiting."
      >
        {drafts.map((batch) => (
          <ProcessRow key={batch.id} batch={batch} onOpen={open} />
        ))}
      </ProcessSection>

      <ProcessSection
        id="finished"
        label="Finished"
        caption="completed, failed or cancelled"
        emptyText="No finished runs yet."
      >
        {finished.map((batch) => (
          <ProcessRow key={batch.id} batch={batch} onOpen={open} />
        ))}
      </ProcessSection>
    </div>
  );
}
