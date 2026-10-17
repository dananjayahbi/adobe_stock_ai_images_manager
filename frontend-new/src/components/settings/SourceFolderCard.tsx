"use client";

import { useEffect, useState } from "react";
import { fetchFsRoot } from "@/lib/fs";
import type { FsRoot } from "@/lib/fs";
import type { UseSettingsResult } from "@/hooks/useSettings";

const inputClass =
  "w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60";

interface Props {
  controller: UseSettingsResult;
}

/**
 * Source folder: where the mobile app's image picker browses. One text field
 * plus a compact `/api/fs/root` status line, so the operator sees immediately
 * whether the saved path actually exists on the server machine.
 */
export default function SourceFolderCard({ controller }: Props) {
  const { settings, draft, isLoading, setField } = controller;
  const [root, setRoot] = useState<FsRoot | null>(null);
  const [checked, setChecked] = useState(false);

  // Fetched on mount and again whenever a save/reset lands (`settings`
  // identity changes), so the line reflects what the server just stored.
  useEffect(() => {
    let stale = false;
    fetchFsRoot()
      .then((data) => {
        if (!stale) {
          setRoot(data);
          setChecked(true);
        }
      })
      .catch(() => {
        if (!stale) {
          setRoot(null);
          setChecked(true);
        }
      });
    return () => {
      stale = true;
    };
  }, [settings]);

  return (
    <section aria-label="Source folder" className="frame-card px-5 py-4">
      <p className="label-caps">Source folder</p>
      <h2 className="mt-1 font-display text-xl text-ink-800">Mobile picker root</h2>
      <p className="mt-1 text-sm text-ink-400">
        The mobile app&apos;s image picker browses this folder.
      </p>

      <div className="mt-4">
        <label htmlFor="set-source-folder" className="label-caps mb-1 block">
          Source folder
        </label>
        <input
          id="set-source-folder"
          type="text"
          value={draft.source_folder}
          disabled={isLoading}
          placeholder="/D/AdobeStock/source"
          onChange={(event) => setField("source_folder", event.target.value)}
          className={inputClass}
        />
        <p className="mt-1 text-xs text-ink-400">
          Absolute path on the server machine — blank unsets it.
        </p>

        {/* Compact fs/root status: path + exists? / missing? / Not set. */}
        <p
          role="status"
          className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1"
        >
          {!checked && (
            <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
              Checking folder…
            </span>
          )}
          {checked && root?.configured && (
            <>
              <span className="min-w-0 max-w-full truncate font-stamp text-[11px] text-ink-600">
                {root.path}
              </span>
              {root.exists ? (
                <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-olive-400">
                  ✓ exists
                </span>
              ) : (
                <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-rust-400">
                  ⚠ missing
                </span>
              )}
            </>
          )}
          {checked && root && !root.configured && (
            <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
              Not set
            </span>
          )}
          {checked && !root && (
            <span className="font-stamp text-[11px] uppercase tracking-[0.14em] text-ink-400">
              Status unavailable
            </span>
          )}
        </p>
      </div>
    </section>
  );
}
