"use client";

import Link from "next/link";
import { useRecords } from "@/hooks/useRecords";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";
import ImageCard from "./ImageCard";

interface LatestGridProps {
  /** Opens the New Batch wizard (wired by the page). */
  onNewBatch: () => void;
}

/** Home page section: the 12 most recently processed images. */
export default function LatestGrid({ onNewBatch }: LatestGridProps) {
  const { page, loading, error } = useRecords({
    limit: 12,
    stageUpdated: true,
    pollMs: 8000,
  });

  const records = page?.items ?? [];

  return (
    <section aria-labelledby="latest-heading">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label-caps">The ledger</p>
          <h2 id="latest-heading" className="font-display text-2xl text-ink-800">
            Latest processed
          </h2>
        </div>
        <Link href="/gallery">
          <Button variant="secondary" size="sm">
            Open gallery →
          </Button>
        </Link>
      </div>

      {error && (
        <p className="mb-4 rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
          {error}
        </p>
      )}

      {loading && records.length === 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className="frame-card h-44 animate-pulse bg-parchment-200"
            />
          ))}
        </div>
      )}

      {!loading && records.length === 0 && !error && (
        <EmptyState
          glyph="№1"
          title="Nothing has been processed yet"
          body="Start a batch to feed the ledger — pick a media type, choose your steps, and run the pipeline."
          action={
            <Button onClick={onNewBatch} size="lg">
              New batch
            </Button>
          }
        />
      )}

      {records.length > 0 && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
          {records.map((record) => (
            <ImageCard key={record.id} record={record} />
          ))}
        </div>
      )}
    </section>
  );
}
