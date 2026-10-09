"use client";

import { useCallback, useMemo, useState } from "react";
import { useRecords } from "@/hooks/useRecords";
import EmptyState from "@/components/ui/EmptyState";
import Button from "@/components/ui/Button";
import GalleryTile from "@/components/gallery/GalleryTile";
import Lightbox from "@/components/gallery/Lightbox";
import type { ImageRecord } from "@/lib/types";

/** Gallery: every processed image, searchable, with a keyboard-driven lightbox. */
export default function GalleryPage() {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  const { page, loading, error } = useRecords({
    limit: 200,
    search,
    stageUpdated: true,
  });

  const records = useMemo(() => page?.items ?? [], [page]);

  const open = useCallback(
    (record: ImageRecord) => {
      const index = records.findIndex((r) => r.id === record.id);
      if (index >= 0) setActiveIndex(index);
    },
    [records]
  );

  const navigate = useCallback(
    (direction: -1 | 1) => {
      setActiveIndex((current) => {
        if (current === null || records.length === 0) return current;
        const next = (current + direction + records.length) % records.length;
        return next;
      });
    },
    [records.length]
  );

  const active = activeIndex !== null ? records[activeIndex] ?? null : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label-caps">The collection</p>
          <h1 className="font-display text-3xl text-ink-800">
            Gallery
            {page && (
              <span className="ml-3 font-stamp text-sm text-ink-400">
                {page.total} plates
              </span>
            )}
          </h1>
        </div>

        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setSearch(draft.trim());
          }}
        >
          <input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => setSearch(draft.trim())}
            placeholder="Search titles, keywords, filenames…"
            className="w-64 rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 placeholder:text-ink-400/70 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
            aria-label="Search the gallery"
          />
          <Button variant="secondary" size="sm" type="submit">
            Search
          </Button>
          {search && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              onClick={() => {
                setDraft("");
                setSearch("");
              }}
            >
              Clear
            </Button>
          )}
        </form>
      </div>

      {error && (
        <p className="rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400" role="alert">
          {error}
        </p>
      )}

      {loading && records.length === 0 && (
        <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="frame-card mb-4 h-40 animate-pulse bg-parchment-200"
            />
          ))}
        </div>
      )}

      {!loading && records.length === 0 && (
        <EmptyState
          glyph="◈"
          title={search ? "No plates match your search" : "The gallery is empty"}
          body={
            search
              ? "Try a different word — search covers titles, descriptions, keywords, categories and filenames."
              : "Processed images appear here as soon as a pipeline step touches them."
          }
        />
      )}

      {records.length > 0 && (
        <div className="columns-2 gap-4 sm:columns-3 lg:columns-4 xl:columns-5 2xl:columns-6">
          {records.map((record) => (
            <GalleryTile key={record.id} record={record} onOpen={open} />
          ))}
        </div>
      )}

      <Lightbox
        record={active}
        onClose={() => setActiveIndex(null)}
        onNavigate={navigate}
      />
    </div>
  );
}
