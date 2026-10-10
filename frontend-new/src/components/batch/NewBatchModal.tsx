"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { createBatch } from "@/lib/batches";
import type { BatchStep, MediaType, StepProfile } from "@/lib/types";
import Modal from "@/components/ui/Modal";
import Button from "@/components/ui/Button";
import MediaTypeStep from "./steps/MediaTypeStep";
import ProfileStep from "./steps/ProfileStep";
import StepsPicker from "./steps/StepsPicker";

interface NewBatchModalProps {
  open: boolean;
  onClose: () => void;
}

type WizardStep = "type" | "profile" | "steps";

const STEP_TITLES: Record<WizardStep, string> = {
  type: "What are we processing?",
  profile: "How should it run?",
  steps: "Which steps?",
};

/**
 * The New Batch wizard.
 *
 * Flow: media type → profile (or custom) → step picker (custom only) →
 * create the draft batch and hand off to the processing page. When a profile
 * is chosen the step picker is skipped entirely — the profile's steps *and
 * configs* arrive on the processing page already filled in.
 */
export default function NewBatchModal({ open, onClose }: NewBatchModalProps) {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>("type");
  const [mediaType, setMediaType] = useState<MediaType | null>(null);
  const [profile, setProfile] = useState<StepProfile | null>(null);
  const [customSteps, setCustomSteps] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wizardSteps: WizardStep[] = useMemo(() => {
    if (!mediaType) return ["type"];
    return profile ? ["type", "profile"] : ["type", "profile", "steps"];
  }, [mediaType, profile]);

  const currentIndex = wizardSteps.indexOf(step);

  const reset = () => {
    setStep("type");
    setMediaType(null);
    setProfile(null);
    setCustomSteps([]);
    setError(null);
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const chooseType = (type: MediaType) => {
    setMediaType(type);
    setProfile(null);
    setCustomSteps([]);
    setStep("profile");
  };

  const chooseProfile = (chosen: StepProfile | null) => {
    setProfile(chosen);
    if (chosen) {
      // Profile selected: skip the picker — its steps ride along.
      setStep("profile");
    } else if (step !== "steps") {
      setStep("steps");
    }
  };

  const toggleStep = (key: string) => {
    setCustomSteps((current) =>
      current.includes(key)
        ? current.filter((k) => k !== key)
        // Newly picked steps join the *end* of the run order; the operator can
        // move them in the list beside the picker.
        : [...current, key]
    );
  };

  const moveStep = (key: string, direction: -1 | 1) => {
    setCustomSteps((current) => {
      const index = current.indexOf(key);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const removeStep = (key: string) => {
    setCustomSteps((current) => current.filter((k) => k !== key));
  };

  const buildSteps = (): BatchStep[] => {
    if (profile) return profile.steps;
    // The order the operator arranged is the order that runs.
    return customSteps.map((key) => ({ key, config: {} }));
  };

  const submit = async () => {
    if (!mediaType) return;
    if (!profile && customSteps.length === 0) {
      setError("Pick at least one step.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const batch = await createBatch({
        media_type: mediaType,
        steps: buildSteps(),
        profile_id: profile?.id,
      });
      reset();
      onClose();
      router.push(`/batch/${batch.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const canGoBack = currentIndex > 0 && !submitting;
  const isLastStep =
    step === "steps" || (step === "profile" && profile !== null);

  const goBack = () => {
    if (submitting) return;
    if (step === "steps") setStep("profile");
    else if (step === "profile") setStep("type");
    else handleClose();
  };

  const goNext = () => {
    if (step === "type" && mediaType) setStep("profile");
    else if (step === "profile" && !profile) setStep("steps");
  };

  const canAdvance = step === "type" ? mediaType !== null : true;

  return (
    <Modal open={open} onClose={handleClose} labelledBy="new-batch-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-4 pt-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="label-caps">New batch</p>
            <h2
              id="new-batch-title"
              className="mt-1 font-display text-2xl text-ink-800"
            >
              {STEP_TITLES[step]}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {wizardSteps.map((s, i) => (
              <span
                key={s}
                className={`h-1.5 w-6 rounded-full transition-colors ${
                  i <= currentIndex ? "bg-oxblood-500" : "bg-parchment-300"
                }`}
                aria-hidden="true"
              />
            ))}
          </div>
        </div>
      </div>

      <div className="px-6 py-5">
        {step === "type" && (
          <MediaTypeStep value={mediaType} onSelect={chooseType} />
        )}
        {step === "profile" && mediaType && (
          <ProfileStep
            mediaType={mediaType}
            selectedId={profile?.id ?? null}
            onSelect={chooseProfile}
          />
        )}
        {step === "steps" && mediaType && (
          <StepsPicker
            mediaType={mediaType}
            selected={customSteps}
            onToggle={toggleStep}
            onMove={moveStep}
            onRemove={removeStep}
          />
        )}

        {error && (
          <p className="mt-4 text-sm text-oxblood-400" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-dashed border-parchment-400 px-6 py-4">
        <Button
          variant="ghost"
          onClick={goBack}
          disabled={submitting && step === "type"}
        >
          {canGoBack ? "Back" : "Cancel"}
        </Button>

        <div className="flex items-center gap-3">
          {step === "profile" && !profile && (
            <span className="text-xs italic text-ink-400">
              or continue with a custom pipeline →
            </span>
          )}
          {isLastStep ? (
            <Button
              onClick={() => void submit()}
              loading={submitting}
              disabled={!profile && customSteps.length === 0}
            >
              Open processing page
            </Button>
          ) : (
            <Button onClick={goNext} disabled={!canAdvance || submitting}>
              Continue
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
