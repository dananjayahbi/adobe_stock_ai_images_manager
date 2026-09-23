"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/cn";

export interface GallerySearchBarProps {
  /** The committed search term. */
  value: string;
  /** Called with the debounced term, or "" when cleared. */
  onChange: (value: string) => void;
  /** How many records the current search matched, for the result line. */
  resultCount: number;
  /** Total records when no search is applied, so "12 of 40" is meaningful. */
  totalCount: number;
  /** True while the term has not yet been committed (still typing). */
  isPending?: boolean;
  className?: string;
}

/** How long to wait after the last keystroke before searching. */
const DEBOUNCE_MS = 300;

/**
 * Search box for the gallery.
 *
 * Two deliberate behaviours:
 *
 * * **Debounced, not on every keystroke.** The search hits the API, and firing a
 *   request per character would queue a dozen of them for a single word — each
 *   one racing the others, which is how a list ends up showing results for a
 *   prefix the operator already moved past.
 * * **The local draft is what the input shows.** Binding the input straight to
 *   the committed value makes it impossible to type while a request is in
 *   flight, because the value snaps back to the last committed term.
 *
 * The result count is shown next to the box rather than as a toast: after a
 * search the operator's first question is "did that find anything", and it has
 * to be answerable without moving the eyes.
 */
export default function GallerySearchBar({
  value,
  onChange,
  resultCount,
  totalCount,
  isPending = false,
  className,
}: GallerySearchBarProps) {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  // Keep the draft in step when the term is changed from outside (a filter reset
  // or a cleared search), but never while the operator is mid-word.
  useEffect(() => {
    setDraft((current) => (current === value ? current : value));
  }, [value]);

  useEffect(() => {
    if (draft === value) return;
    const timer = setTimeout(() => onChange(draft), DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `onChange` and `value` are intentionally excluded: including them resets
    // the timer on every parent render, so the debounce would never elapse while
    // the page polls.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const isSearching = value.trim().length > 0;

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="relative min-w-0 flex-1 sm:max-w-sm">
        <Search
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-navy-500"
          aria-hidden
        />
        <input
          ref={inputRef}
          type="search"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Enter commits immediately rather than waiting out the debounce.
            if (event.key === "Enter") onChange(draft);
            if (event.key === "Escape") {
              setDraft("");
              onChange("");
            }
          }}
          placeholder="Search titles, keywords, filenames…"
          aria-label="Search published images"
          className={cn(
            "w-full rounded-lg border border-navy-700/60 bg-navy-900/60 py-1.5 pl-8 pr-8",
            "text-xs text-navy-50 placeholder:text-navy-500",
            "focus:border-accent-500/70 focus:outline-none focus:ring-1 focus:ring-accent-500/40",
            // A native clear button would double up with ours below.
            "[&::-webkit-search-cancel-button]:appearance-none"
          )}
        />
        {draft ? (
          <button
            type="button"
            onClick={() => {
              setDraft("");
              onChange("");
              inputRef.current?.focus();
            }}
            aria-label="Clear search"
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-navy-500 transition-colors hover:text-navy-200"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
          </button>
        ) : null}
      </div>

      <span className="text-xs text-navy-400" aria-live="polite">
        {isSearching ? (
          <>
            {resultCount} of {totalCount} match
            {resultCount === 1 ? "" : "es"}
            {isPending ? " …" : ""}
          </>
        ) : null}
      </span>
    </div>
  );
}
