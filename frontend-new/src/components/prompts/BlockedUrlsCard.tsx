"use client";

/**
 * Blocked URLs card: pages the research agent already failed to read.
 *
 * A small visibility panel, not a control surface — the list is written by the
 * fetch tool itself, and the only operator actions needed are the two that put
 * a URL back in play: unblock one (the site may have stopped blocking) and
 * clear all (start measuring from zero).
 *
 * Unlike `PrioritySourcesCard`, this card renders **nothing** when the list is
 * empty: that card's empty state *is* its upload control, so it has something
 * to show and do. An empty blocked list has neither, and a permanently visible
 * "0 blocked" panel in the settings dialog is noise.
 */
import { Ban, RotateCcw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import Button from "@/components/ui/Button";
import {
  clearBlockedUrls,
  fetchBlockedUrls,
  unblockUrl,
  type BlockedUrlList,
} from "@/lib/research";
import { errorClass } from "./fieldStyles";

/**
 * Render a stored UTC ISO timestamp as a compact local-looking date-time.
 *
 * The store always writes `...T10:58:49+00:00`; slicing rather than
 * `toLocaleString` keeps the panel's output identical across browsers and
 * locales, which matters when someone is comparing runs.
 */
function formatBlockedAt(iso: string): string {
  return `${(iso || "").slice(0, 16).replace("T", " ")} UTC`;
}

export default function BlockedUrlsCard() {
  const [list, setList] = useState<BlockedUrlList | null>(null);
  const [isBusy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchBlockedUrls()
      .then((next) => {
        if (!cancelled) setList(next);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Could not load blocked URLs.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUnblock = useCallback(async (url: string) => {
    setError(null);
    setBusy(true);
    try {
      // The response is the full updated list, so one round-trip both acts
      // and repaints — no refetch that could show a stale row.
      setList(await unblockUrl(url));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unblock the URL.");
    } finally {
      setBusy(false);
    }
  }, []);

  const handleClear = useCallback(async () => {
    setError(null);
    setBusy(true);
    try {
      setList(await clearBlockedUrls());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not clear the list.");
    } finally {
      setBusy(false);
    }
  }, []);

  // Nothing blocked (and nothing to report) → nothing to render.
  if (!error && (!list || list.entries.length === 0)) return null;

  const entries = list?.entries ?? [];
  const total = list?.total ?? 0;

  return (
    <section aria-label="Blocked URLs" className="frame-card px-5 py-4">
      <div className="flex items-center gap-2">
        <Ban className="h-4 w-4 text-oxblood-400" aria-hidden />
        <p className="label-caps">Blocked URLs</p>
        {total > 0 && (
          <span className="ml-auto rounded-sm border border-oxblood-500/60 bg-oxblood-400/10 px-1.5 py-0.5 font-stamp text-[10px] uppercase tracking-[0.14em] text-oxblood-400">
            {total} blocked
          </span>
        )}
      </div>

      <p className="mt-2 text-sm text-ink-400">
        Pages that failed to load (timeouts, HTTP errors, anti-bot walls). The
        agent refuses these before connecting; unblock one to let it try again.
      </p>

      {entries.length > 0 && (
        <ul className="mt-3 space-y-2">
          {entries.map((entry) => (
            <li
              key={entry.url}
              className="rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs text-ink-800" title={entry.url}>
                    {entry.url}
                  </p>
                  <p className="mt-0.5 text-xs text-ink-400">
                    {entry.host || "unknown host"} · failed {entry.failures}× ·{" "}
                    {formatBlockedAt(entry.blocked_at)}
                  </p>
                  <p className="mt-0.5 break-words text-xs text-oxblood-400">
                    {entry.error}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  type="button"
                  disabled={isBusy}
                  onClick={() => void handleUnblock(entry.url)}
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                  Unblock
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {total > 0 && (
          <Button
            size="sm"
            variant="ghost"
            type="button"
            disabled={isBusy}
            onClick={() => void handleClear()}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
            Clear all
          </Button>
        )}
      </div>

      {error && (
        <p className={`${errorClass} mt-2`} role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
