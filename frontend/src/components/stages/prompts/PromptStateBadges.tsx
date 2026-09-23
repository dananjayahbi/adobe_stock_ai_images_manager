"use client";

import { Archive, Check, Link2, Link2Off } from "lucide-react";

import { cn } from "@/lib/cn";
import type { Prompt } from "@/lib/prompts";

export interface PromptStateBadgesProps {
  prompt: Prompt;
}

/** Status-axis badge: has the prompt been consumed? */
function StatusBadge({ prompt }: PromptStateBadgesProps) {
  if (prompt.status === "ARCHIVED") {
    return (
      <span
        className="inline-flex shrink-0 items-center gap-1 rounded-full border border-navy-600/60 bg-navy-800/70 px-1.5 py-0.5 text-[10px] font-semibold text-navy-300"
        title="Archived — filed away"
      >
        <Archive className="h-2.5 w-2.5" aria-hidden />
        Archived
      </span>
    );
  }

  if (prompt.status === "USED") {
    return (
      <span
        className="inline-flex shrink-0 items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-200"
        title="Used — this prompt has been consumed"
      >
        <Check className="h-2.5 w-2.5" aria-hidden />
        Used
      </span>
    );
  }

  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-navy-600/60 bg-navy-800/70 px-1.5 py-0.5 text-[10px] font-semibold text-navy-300"
      title="Draft — not consumed yet"
    >
      Unused
    </span>
  );
}

/**
 * Binding-axis badge: is the prompt linked to collected images?
 *
 * Rendered separately from the status badge because the two are independent —
 * a prompt can be *Used* and *Unbound* at once (consumed elsewhere, nothing
 * collected here), and that combination is the single most useful thing the
 * library can tell the operator. Merging the badges into one would hide it.
 *
 * Only shown when the prompt is used, since an unused draft is trivially
 * unbound and a second badge would be noise on most rows.
 */
function BindingBadge({ prompt }: PromptStateBadgesProps) {
  const isBound = prompt.bound_count > 0;

  if (!isBound) {
    return (
      <span
        className="inline-flex shrink-0 items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-200"
        title="Unbound — no image collected from this prompt"
      >
        <Link2Off className="h-2.5 w-2.5" aria-hidden />
        Unbound
      </span>
    );
  }

  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-accent-500/40 bg-accent-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent-200"
      title={`Bound to ${prompt.bound_count} image(s)`}
    >
      <Link2 className="h-2.5 w-2.5" aria-hidden />
      Bound
    </span>
  );
}

/**
 * Both state badges for one prompt block.
 *
 * The two badges read two different fields on purpose: `status` for the first,
 * `bound_count` for the second. They are never derived from each other.
 */
export function PromptStateBadges({ prompt }: PromptStateBadgesProps) {
  return (
    <span className={cn("flex shrink-0 items-center gap-1")}>
      <StatusBadge prompt={prompt} />
      {prompt.status !== "ARCHIVED" ? <BindingBadge prompt={prompt} /> : null}
    </span>
  );
}

export default PromptStateBadges;
