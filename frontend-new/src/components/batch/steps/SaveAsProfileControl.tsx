"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import SaveProfileDialog from "@/components/process/SaveProfileDialog";
import { createProfile } from "@/lib/profiles";
import type { BatchStep, MediaType } from "@/lib/types";

interface SaveAsProfileControlProps {
  mediaType: MediaType;
  /** Step keys currently ticked in the picker. */
  selected: string[];
}

/**
 * "Save as profile" affordance for the New Batch wizard's step picker.
 *
 * The wizard only *consumes* profiles (ProfileStep), so without this control
 * the only way to create one was the processing page. This wraps the shared
 * name dialog plus the create call in one self-contained unit: it builds the
 * steps in the operator's run order, posts them, and confirms inline so the
 * operator knows the recipe is now offered back in this wizard.
 */
export default function SaveAsProfileControl({
  mediaType,
  selected,
}: SaveAsProfileControlProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null);

  if (selected.length === 0) return null;

  // `selected` already arrives in run order — saving must not re-sort it.
  const steps: BatchStep[] = selected.map((key) => ({
    key,
    config: {},
  }));

  const handleSave = async (name: string) => {
    await createProfile({ name, media_type: mediaType, steps });
    setSavedName(name);
  };

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-dashed border-parchment-400 bg-parchment-100/60 px-4 py-3">
        <p className="text-sm text-ink-400">
          {savedName ? (
            <>
              Profile{" "}
              <span className="font-medium text-ink-800">“{savedName}”</span>{" "}
              saved — go Back to pick it under “How should it run?”.
            </>
          ) : (
            <>
              {selected.length} step{selected.length === 1 ? "" : "s"} selected.
              Keep this exact recipe for later{" "}
              {mediaType === "png" ? "PNG" : "photo"} batches.
            </>
          )}
        </p>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setDialogOpen(true)}
        >
          Save as profile
        </Button>
      </div>

      <SaveProfileDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSave={handleSave}
        mediaType={mediaType}
      />
    </>
  );
}
