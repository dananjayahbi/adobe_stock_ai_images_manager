"use client";

import { useEffect, useState } from "react";
import Badge from "@/components/ui/Badge";
import EmptyState from "@/components/ui/EmptyState";
import { deleteProfile, listProfiles } from "@/lib/profiles";
import type { MediaType, StepProfile } from "@/lib/types";

interface Props {
  mediaType: MediaType;
  /** Existing profile selected by the operator, if any. */
  selectedId: string | null;
  onSelect: (profile: StepProfile | null) => void;
}

/**
 * Wizard step 2 — use a saved profile, or go custom.
 *
 * Selecting a profile does not lock the wizard in: "Custom pipeline" is always
 * offered as the alternative, and picking it keeps the media-type choice.
 */
export default function ProfileStep({ mediaType, selectedId, onSelect }: Props) {
  const [profiles, setProfiles] = useState<StepProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      setProfiles(await listProfiles(mediaType));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaType]);

  const remove = async (id: string) => {
    try {
      await deleteProfile(id);
      if (selectedId === id) onSelect(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const customActive = selectedId === null;

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={() => onSelect(null)}
        aria-pressed={customActive}
        className={`frame-card w-full px-5 py-4 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-brass-400 ${
          customActive
            ? "-translate-y-0.5 border-oxblood-500 ring-1 ring-oxblood-500"
            : "hover:-translate-y-0.5"
        }`}
      >
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="font-display text-lg text-ink-800">
              Custom pipeline
            </h3>
            <p className="mt-1 text-sm text-ink-400">
              Pick the steps yourself on the next screen; configure them on the
              processing page.
            </p>
          </div>
          {customActive && <span className="stamp">Selected</span>}
        </div>
      </button>

      <div className="label-caps">
        Saved profiles{" "}
        {loading ? "· loading…" : `· ${profiles.length} for ${mediaType}`}
      </div>

      {error && (
        <p className="text-sm text-oxblood-400" role="alert">
          {error}
        </p>
      )}

      {!loading && profiles.length === 0 && !error && (
        <p className="text-sm italic text-ink-400">
          No profiles yet. You can save one from the processing page after
          configuring a run.
        </p>
      )}

      <div className="grid gap-3">
        {profiles.map((profile) => {
          const active = selectedId === profile.id;
          return (
            <div
              key={profile.id}
              className={`frame-card group px-5 py-4 transition-all ${
                active
                  ? "-translate-y-0.5 border-oxblood-500 ring-1 ring-oxblood-500"
                  : "hover:-translate-y-0.5"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <button
                  type="button"
                  onClick={() => onSelect(profile)}
                  aria-pressed={active}
                  className="flex-1 text-left focus:outline-none"
                >
                  <div className="flex items-center gap-2">
                    <h3 className="font-display text-lg text-ink-800">
                      {profile.name}
                    </h3>
                    {active && <span className="stamp">Selected</span>}
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {profile.steps.map((step) => (
                      <Badge key={step.key} tone="info">
                        {step.key.replace("_", " ")}
                      </Badge>
                    ))}
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => remove(profile.id)}
                  className="font-stamp text-[10px] uppercase tracking-[0.14em] text-ink-400 underline-offset-2 transition-colors hover:text-oxblood-400 hover:underline"
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {profiles.length === 0 && !loading && (
        <div className="pt-2">
          <EmptyState
            glyph="§"
            title="No step profiles yet"
            body="Configure a run on the processing page and press “Save as profile” to keep the recipe."
          />
        </div>
      )}
    </div>
  );
}
