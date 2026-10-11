"use client";

import type { UseSettingsResult } from "@/hooks/useSettings";

const inputClass =
  "w-full rounded-sm border border-parchment-500 bg-parchment-50 px-3 py-2 text-sm text-ink-800 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400 disabled:opacity-60";

interface Props {
  controller: UseSettingsResult;
}

/**
 * Metadata generation options: how many keywords to ask for, how hard to
 * pace the calls, and any operator instruction appended to the prompt.
 *
 * These are *content* choices, deliberately separate from the gateway card's
 * endpoint choices - a save here never has to touch the credential fields.
 */
export default function MetadataSettingsCard({ controller }: Props) {
  const { settings, draft, isLoading, setField } = controller;
  const bounds = settings?.bounds;
  const instructionsLength = draft.metadata_extra_instructions.length;

  return (
    <section aria-label="Metadata generation" className="frame-card px-5 py-4">
      <p className="label-caps">Metadata generation</p>
      <h2 className="mt-1 font-display text-xl text-ink-800">
        Titles, keywords &amp; pacing
      </h2>
      <p className="mt-1 text-sm text-ink-400">
        Applies to the next metadata generation — no restart. Keyword counts are
        capped at Adobe&apos;s published ceiling of 49.
      </p>

      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="set-keyword-target" className="label-caps mb-1 block">
            Keywords to request
          </label>
          <input
            id="set-keyword-target"
            type="number"
            value={draft.metadata_keyword_target}
            disabled={isLoading}
            min={bounds?.min_keyword_target}
            max={bounds?.max_keyword_target}
            onChange={(event) => setField("metadata_keyword_target", event.target.value)}
            className={inputClass}
          />
          <p className="mt-1 text-xs text-ink-400">
            The first 10 carry the most search weight — 30–49 is the sweet spot.
          </p>
        </div>

        <div>
          <label htmlFor="set-delay" className="label-caps mb-1 block">
            Delay between calls (s)
          </label>
          <input
            id="set-delay"
            type="number"
            value={draft.metadata_delay_seconds}
            disabled={isLoading}
            min={bounds?.min_metadata_delay}
            max={bounds?.max_metadata_delay}
            step={0.5}
            onChange={(event) => setField("metadata_delay_seconds", event.target.value)}
            className={inputClass}
          />
          <p className="mt-1 text-xs text-ink-400">
            Pacing between images to stay under rate limits.
          </p>
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="set-instructions" className="label-caps mb-1 block">
            Extra instructions
          </label>
          <textarea
            id="set-instructions"
            rows={4}
            value={draft.metadata_extra_instructions}
            disabled={isLoading}
            maxLength={bounds?.max_extra_instructions}
            placeholder='e.g. Prefer "studio shot" over "close-up". Never mention the word minimalist.'
            onChange={(event) =>
              setField("metadata_extra_instructions", event.target.value)
            }
            className={`${inputClass} resize-y`}
          />
          <p className="mt-1 text-xs text-ink-400">
            Appended to the metadata prompt after its rules — follow them unless
            they contradict Adobe&apos;s requirements.
            {bounds && (
              <>
                {" "}
                {instructionsLength}/{bounds.max_extra_instructions} characters.
              </>
            )}
          </p>
        </div>

        <div className="sm:col-span-2">
          <label htmlFor="set-priority-terms" className="label-caps mb-1 block">
            Priority keyword terms (top-10)
          </label>
          <textarea
            id="set-priority-terms"
            rows={3}
            value={draft.metadata_priority_terms}
            disabled={isLoading}
            maxLength={bounds?.max_priority_terms_chars}
            placeholder="e.g. background, texture, wall art, banner"
            onChange={(event) =>
              setField("metadata_priority_terms", event.target.value)
            }
            className={`${inputClass} resize-y`}
          />
          <p className="mt-1 text-xs text-ink-400">
            Comma-separated high-intent commercial terms, stably moved to the
            first 10 keyword positions (Adobe weights them most). Aesthetic hype
            words — photorealistic, hyper-detailed, trending on artstation — are
            filtered out automatically.
            {bounds && (
              <>
                {" "}
                {draft.metadata_priority_terms.length}/
                {bounds.max_priority_terms_chars} characters.
              </>
            )}
          </p>
        </div>
      </div>
    </section>
  );
}
