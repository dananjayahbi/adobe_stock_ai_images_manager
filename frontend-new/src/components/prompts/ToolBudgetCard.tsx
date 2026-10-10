"use client";

/**
 * The research tool budget: how many tool calls a research run may make.
 *
 * Fetched straight from `GET /api/settings` rather than the settings page's
 * `useSettings` hook — this card owns one field and must not drag the whole
 * settings controller (or its save-everything payload) into the prompts page.
 * The server's own `bounds` decide the input's limits, so the range cannot
 * drift from what `PUT /api/settings` will accept.
 */
import { useCallback, useEffect, useState } from "react";

import Button from "@/components/ui/Button";
import { api } from "@/lib/client";
import { errorClass, hintClass, inputClass, labelClass } from "./fieldStyles";

/** The slice of `SettingsResponse` this card reads. */
interface ToolBudgetSettings {
  research_max_tool_calls: number;
  bounds: {
    min_tool_calls: number;
    max_tool_calls: number;
  };
}

/** The slice of `SettingsUpdateRequest` this card sends. */
interface ToolBudgetUpdate {
  research_max_tool_calls: number;
}

export default function ToolBudgetCard() {
  const [stored, setStored] = useState<ToolBudgetSettings | null>(null);
  const [draft, setDraft] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .get<ToolBudgetSettings>("/api/settings")
      .then(({ data }) => {
        if (cancelled) return;
        setStored(data);
        setDraft(String(data.research_max_tool_calls));
        setError(null);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Could not load the tool budget."
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const bounds = stored?.bounds;
  const isDirty =
    stored !== null && draft !== String(stored.research_max_tool_calls);

  const save = useCallback(async () => {
    if (!stored) return;
    const next = Number(draft);
    if (!Number.isFinite(next)) {
      setError("Enter a number of tool calls.");
      return;
    }
    setSaving(true);
    setNotice(null);
    try {
      const { data } = await api.put<ToolBudgetSettings>("/api/settings", {
        research_max_tool_calls: next,
      } satisfies ToolBudgetUpdate);
      setStored(data);
      setDraft(String(data.research_max_tool_calls));
      setError(null);
      setNotice("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the budget.");
    } finally {
      setSaving(false);
    }
  }, [draft, stored]);

  return (
    <section aria-label="Research tool budget" className="frame-card px-5 py-4">
      <p className="label-caps">Research tool budget</p>
      <p className="mt-1 text-sm text-ink-400">
        How many tool calls a research run may make before it must answer.
      </p>

      {isLoading ? (
        <div className="mt-4 h-16 animate-pulse rounded-sm bg-parchment-200" />
      ) : (
        <div className="mt-4">
          <label htmlFor="tool-budget" className={labelClass}>
            Max tool calls
          </label>
          <input
            id="tool-budget"
            type="number"
            min={bounds?.min_tool_calls}
            max={bounds?.max_tool_calls}
            value={draft}
            disabled={isSaving}
            onChange={(event) => setDraft(event.target.value)}
            className={`${inputClass} max-w-[7rem]`}
          />
          {bounds && (
            <p className={hintClass}>
              Between {bounds.min_tool_calls} and {bounds.max_tool_calls} calls.
            </p>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              type="button"
              loading={isSaving}
              disabled={!isDirty}
              onClick={() => void save()}
            >
              Save
            </Button>
            {notice && (
              <span className="text-xs text-olive-400" role="status">
                {notice}
              </span>
            )}
          </div>

          {error && <p className={`mt-2 ${errorClass}`} role="alert">{error}</p>}
        </div>
      )}
    </section>
  );
}
