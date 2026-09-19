"use client";

import { AlertCircle, Loader2, RefreshCw, Table } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchUploadTable, type UploadTableItem } from "@/lib/api";
import { readUploadTableSelection } from "@/lib/uploadTableStore";

import UploadTable from "./UploadTable";

interface UploadTableViewProps {
  token: string | null;
  /** Fallback ids supplied directly via `?ids=a,b,c`. */
  idsFromQuery: string[];
}

/** Loads the selected records and renders the copy/paste upload table. */
export default function UploadTableView({
  token,
  idsFromQuery,
}: UploadTableViewProps) {
  const [items, setItems] = useState<UploadTableItem[]>([]);
  const [missing, setMissing] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Serialize the selection to a primitive so the load effect has a stable
  // dependency - array identity changes on every render would cause a
  // re-fetch loop.
  const idsKey = useMemo(() => {
    const resolved = token ? readUploadTableSelection(token) : null;
    const source = resolved && resolved.length > 0 ? resolved : idsFromQuery;
    return source.join(",");
  }, [token, idsFromQuery]);

  const ids = useMemo(
    () => (idsKey ? idsKey.split(",").filter(Boolean) : []),
    [idsKey]
  );

  const load = useCallback(async () => {
    const currentIds = idsKey ? idsKey.split(",").filter(Boolean) : [];
    if (currentIds.length === 0) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const response = await fetchUploadTable(currentIds);
      setItems(response.items);
      setMissing(response.missing);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to build the upload table."
      );
    } finally {
      setIsLoading(false);
    }
  }, [idsKey]);

  useEffect(() => {
    void load();
  }, [load]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-xl border border-dashed border-zinc-800 py-16 text-zinc-500">
        <Loader2 className="h-5 w-5 animate-spin" />
        Building upload table…
      </div>
    );
  }

  if (ids.length === 0) {
    return (
      <EmptyState
        title="No images were selected"
        message="Go back to the gallery, select the images you want to submit, then press “Generate upload table”."
      />
    );
  }

  if (error) {
    return (
      <div className="space-y-4">
        <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-1.5 rounded-md border border-red-400/40 px-2.5 py-1 text-xs font-medium transition-colors hover:border-red-300"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="Nothing to show"
        message="The selected images could not be found. They may have been deleted."
      />
    );
  }

  return (
    <div className="space-y-4">
      {missing.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            {missing.length} selected image(s) no longer exist and were skipped.
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="inline-flex items-center gap-1.5 text-sm text-zinc-400">
          <Table className="h-4 w-4" />
          {items.length} row(s) ready to copy
        </p>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      <UploadTable items={items} />
    </div>
  );
}

function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-zinc-800 py-16 text-center">
      <Table className="h-7 w-7 text-zinc-700" />
      <div>
        <p className="text-sm font-medium text-zinc-300">{title}</p>
        <p className="mt-1 max-w-md text-xs text-zinc-500">{message}</p>
      </div>
      <Link
        href="/gallery"
        className="rounded-md border border-sky-500/50 bg-sky-500/10 px-3.5 py-1.5 text-xs font-medium text-sky-300 transition-colors hover:border-sky-400"
      >
        Back to gallery
      </Link>
    </div>
  );
}
