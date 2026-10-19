"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import Modal from "@/components/ui/Modal";
import {
  checkPromote,
  fetchPromoteJob,
  runPromote,
  type PromoteCheckItem,
  type PromoteJob,
} from "@/lib/promote";

interface PromoteDialogProps {
  recordIds: string[];
  open: boolean;
  onClose: () => void;
  /** Called after a finished job so the gallery can reload. */
  onPromoted: () => void;
}

const POLL_MS = 1500;

/** Step state → badge tone + glyph. */
function stepMarker(ok: boolean) {
  return ok
    ? { glyph: "✓", className: "text-olive-400" }
    : { glyph: "✕", className: "text-rust-400" };
}

/** One record's row: filename + per-step pass/miss with reasons. */
function CheckRow({ item }: { item: PromoteCheckItem }) {
  return (
    <div className="rounded-sm border border-parchment-400/60 bg-parchment-50/40 px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <p className="min-w-0 truncate text-xs text-ink-800" title={item.filename}>
          {item.filename}
        </p>
        {item.blocker ? (
          <Badge tone="danger">Blocked</Badge>
        ) : item.steps.every((step) => step.ok) ? (
          <Badge tone="success">Ready</Badge>
        ) : (
          <Badge tone="warn">Needs work</Badge>
        )}
      </div>
      {item.blocker ? (
        <p className="mt-1 text-[11px] text-rust-400">{item.blocker}</p>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {item.steps.map((step) => {
            const marker = stepMarker(step.ok);
            return (
              <li key={step.key} className="flex items-baseline gap-1.5 text-[11px]">
                <span className={marker.className}>{marker.glyph}</span>
                <span className="shrink-0 text-ink-600">{step.label}:</span>
                <span className="min-w-0 text-ink-400">{step.detail}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/** Live per-record results while the job runs (and after it finishes). */
function JobResults({ job }: { job: PromoteJob }) {
  return (
    <div className="space-y-1">
      {job.items.map((item) => {
        const tone =
          item.status === "succeeded"
            ? "text-olive-400"
            : item.status === "failed"
              ? "text-rust-400"
              : "text-ink-400";
        return (
          <div
            key={item.record_id}
            className="rounded-sm border border-parchment-400/60 bg-parchment-50/40 px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="min-w-0 truncate text-xs text-ink-800">{item.filename}</p>
              <span className={`font-stamp text-[10px] uppercase ${tone}`}>
                {item.status}
              </span>
            </div>
            {item.message && (
              <p className="mt-0.5 text-[11px] leading-relaxed text-ink-400">
                {item.message}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Pre-flight modal for pushing images to the ready-to-upload state.
 *
 * Opening runs the *check* only: each selected image shows which of the three
 * requirements (Acceptance QC, embedded sRGB profile, metadata & keywords) it
 * is missing. Confirming runs only those gaps per image — an image that
 * already has metadata never pays for a second generation — and promotes the
 * ones that end up passing. The run itself is a polled background job.
 */
export default function PromoteDialog({
  recordIds,
  open,
  onClose,
  onPromoted,
}: PromoteDialogProps) {
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [items, setItems] = useState<PromoteCheckItem[]>([]);

  const [job, setJob] = useState<PromoteJob | null>(null);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const requestId = useRef(0);
  const promotedRef = useRef(false);

  const loadCheck = useCallback(async () => {
    if (recordIds.length === 0) return;
    const id = ++requestId.current;
    setChecking(true);
    setCheckError(null);
    try {
      const data = await checkPromote(recordIds);
      if (id === requestId.current) setItems(data.items);
    } catch (err) {
      if (id === requestId.current) {
        setCheckError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      if (id === requestId.current) setChecking(false);
    }
  }, [recordIds]);

  // Fresh pre-flight every time the dialog opens; the run state resets with it.
  useEffect(() => {
    if (!open) return;
    setJob(null);
    setRunError(null);
    promotedRef.current = false;
    void loadCheck();
  }, [open, loadCheck]);

  // Poll the job while it runs; a finished job pauses the timer (the interval
  // stays so a re-run resumes), and completion fires the gallery reload once.
  useEffect(() => {
    if (!job || job.status === "running") return;
    if (!promotedRef.current) {
      promotedRef.current = true;
      onPromoted();
    }
  }, [job, onPromoted]);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const fresh = await fetchPromoteJob(job.id);
        setJob(fresh);
      } catch {
        /* transient poll failure — retried on the next tick */
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [job]);

  const startRun = useCallback(async () => {
    setStarting(true);
    setRunError(null);
    try {
      const started = await runPromote(recordIds);
      setJob(started);
    } catch (err) {
      setRunError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }, [recordIds]);

  const promotable = items.filter((item) => !item.blocker);
  const needsWork = promotable.filter((item) =>
    item.steps.some((step) => !step.ok)
  );
  const allDone = job != null && job.status !== "running";
  const running = job?.status === "running" || starting;

  return (
    <Modal open={open} onClose={onClose} width="max-w-2xl" labelledBy="promote-title">
      <div className="border-b border-dashed border-parchment-400 px-6 pb-3 pt-4">
        <p className="label-caps">Gallery</p>
        <h2 id="promote-title" className="mt-0.5 font-display text-xl text-ink-800">
          Push to ready-to-upload
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-ink-400">
          Each image is checked against the three upload requirements — Acceptance
          QC, an embedded sRGB profile, and metadata &amp; keywords. Only the
          missing steps run, per image; images that end up passing move to
          <span className="font-stamp text-[11px]"> METADATA READY</span>.
        </p>
      </div>

      <div className="max-h-[55vh] overflow-y-auto px-6 py-4">
        {checkError && (
          <p
            className="mb-3 cursor-pointer rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
            role="alert"
            onClick={() => setCheckError(null)}
          >
            {checkError}
          </p>
        )}
        {runError && (
          <p
            className="mb-3 cursor-pointer rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-3 py-2 text-sm text-oxblood-400"
            role="alert"
            onClick={() => setRunError(null)}
          >
            {runError}
          </p>
        )}

        {checking && items.length === 0 && (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded-sm bg-parchment-200" />
            ))}
          </div>
        )}

        {/* Pre-flight list — hidden once a run is underway: the job's own
            per-record results replace it, so the panel never shows two
            conflicting states of the same image. */}
        {!running && !allDone && items.length > 0 && (
          <div className="space-y-2">
            <p className="label-caps">
              {items.length} image(s) · {needsWork.length} need work
            </p>
            {items.map((item) => (
              <CheckRow key={item.record_id} item={item} />
            ))}
          </div>
        )}

        {job && (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="label-caps">
                {allDone ? "Finished" : "Running"} · {job.succeeded} promoted ·{" "}
                {job.failed} failed · {job.skipped} skipped
              </p>
              {job.status === "running" && (
                <span className="font-stamp text-[10px] uppercase text-ink-400">
                  {Math.round(job.progress * 100)}%
                </span>
              )}
            </div>
            <div className="h-1 w-full overflow-hidden rounded-full bg-parchment-200">
              <div
                className="h-full bg-oxblood-500 transition-all"
                style={{ width: `${Math.round(job.progress * 100)}%` }}
              />
            </div>
            <JobResults job={job} />
          </div>
        )}
      </div>

      <div className="flex justify-end gap-2 border-t border-dashed border-parchment-400 px-6 py-4">
        <Button variant="ghost" size="sm" type="button" onClick={onClose}>
          {allDone ? "Close" : "Cancel"}
        </Button>
        {!allDone && (
          <Button
            size="sm"
            type="button"
            onClick={() => void startRun()}
            loading={running}
            disabled={running || promotable.length === 0}
            title={
              promotable.length === 0
                ? "No eligible image can be promoted."
                : undefined
            }
          >
            Run missing steps ({promotable.length} image(s))
          </Button>
        )}
      </div>
    </Modal>
  );
}
