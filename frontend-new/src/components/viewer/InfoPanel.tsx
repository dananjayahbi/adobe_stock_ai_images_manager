"use client";

import { useCallback, useEffect, useState } from "react";
import Badge from "@/components/ui/Badge";
import Button from "@/components/ui/Button";
import JsonValue, { isEmptyValue } from "@/components/viewer/JsonValue";
import { approveRecord, changeRecordState } from "@/lib/records";
import {
  APPROVABLE_STATES,
  flagsFromLegacy,
  flagLabel,
  flagTone,
  LIFECYCLE_STATES,
  orderFlags,
  stateFromLegacy,
  stateLabel,
  stateTone,
  STATE_LABELS,
} from "@/lib/states";
import type { ImageLifecycleState, ImageRecord, ImageStatus } from "@/lib/types";

/**
 * Right-side details panel for the viewer: every field the backend's
 * `RecordResponse` carries for the record — metadata, pipeline state,
 * QC/compatibility numbers, names and technical facts — grouped under
 * stamped section headers.
 *
 * Sections render only when they have something to say, so a freshly
 * collected record never shows empty "metadata" boxes; rows without a
 * value are omitted (or show "—" when the fact itself matters).
 */

/** Human labels mirroring the gallery FilterBar's stage options. */
const STAGE_LABELS: Record<string, string> = {
  COLLECTED: "Collected",
  OCR_CLEAR: "OCR clear",
  OCR_REJECTED: "OCR rejected",
  UPSCALED: "Upscaled",
  REFINED: "Refined",
  COMPATIBLE: "Compatible",
  INCOMPATIBLE: "Incompatible",
  METADATA_READY: "Metadata ready",
  PUBLISHED: "Published",
  QUARANTINED: "Quarantined",
};

type Tone = "neutral" | "success" | "warn" | "danger" | "info";

const STATUS_TONES: Record<ImageStatus, Tone> = {
  PENDING: "neutral",
  AUDITING: "info",
  PASSED: "success",
  FLAGGED: "warn",
  APPROVED: "success",
  READY: "success",
};

function formatDate(value?: string | null): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** Bytes → "843 B" / "312.5 KB" / "4.2 MB". */
function formatFileSize(bytes?: number): string | undefined {
  if (bytes == null) return undefined;
  const KB = 1024;
  const MB = 1024 * KB;
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(1)} MB`;
}

/** Short id for dense rows; the full value moves to the `title` attribute. */
function shortId(id?: string | null): { value: string; title: string } | undefined {
  if (!id) return undefined;
  return { value: id.length > 13 ? `${id.slice(0, 8)}…` : id, title: id };
}

function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage.replace(/_/g, " ");
}

/** Section wrapper: stamped header, content only when a child exists. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="px-4 py-3">
      <h3 className="label-caps mb-1.5">{title}</h3>
      {children}
    </section>
  );
}

interface RowProps {
  label: string;
  /** Missing/empty values drop the row entirely (the "—" case passes "—"). */
  value?: string | number | boolean | null;
  /** Tooltip override — long values default to their own full text. */
  title?: string;
  /** Monospace + muted, for paths and ids. */
  mono?: boolean;
  /** Let a long value wrap instead of truncating to one line. */
  wrap?: boolean;
}

function Row({ label, value, title, mono, wrap }: RowProps) {
  if (value == null || value === "") return null;
  const text = String(value);
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="label-caps shrink-0">{label}</span>
      <span
        className={`min-w-0 text-right text-xs text-ink-200 ${
          mono ? "font-stamp text-[11px] text-ink-400" : ""
        } ${wrap ? "break-words whitespace-pre-wrap" : "truncate"}`}
        title={title ?? text}
      >
        {text}
      </span>
    </div>
  );
}

/** Label + badge(s) row — facts that render as stamps, not plain text. */
function BadgeRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-0.5">
      <span className="label-caps shrink-0">{label}</span>
      <span className="flex min-w-0 flex-wrap items-center justify-end gap-1">
        {children}
      </span>
    </div>
  );
}

/** Wraps a list of keywords/flags as small chips. */
function Chips({ items, tone = "" }: { items: string[]; tone?: string }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((item) => (
        <span
          key={item}
          className={`rounded-sm border px-1.5 py-0.5 text-[11px] ${
            tone ||
            "border-parchment-500/50 bg-parchment-50/10 text-ink-200"
          }`}
        >
          {item}
        </span>
      ))}
    </div>
  );
}

/** Key/value rows for a JSON column (`stage_details`, `acceptance_report`). */
function JsonRows({ data }: { data: Record<string, unknown> }) {
  const rows = Object.entries(data).filter(([, value]) => !isEmptyValue(value));
  if (rows.length === 0) return null;
  return (
    <dl className="mt-1 space-y-0.5">
      {rows.map(([key, value]) => (
        <JsonValue key={key} label={key.replace(/_/g, " ")} value={value} />
      ))}
    </dl>
  );
}

interface InfoPanelProps {
  record: ImageRecord;
  /** Closes the panel — wired to the ✕ in the sticky header. */
  onClose: () => void;
  /** Fired after a successful state change so the page can refresh the record. */
  onRecordChanged?: () => void;
}

export default function InfoPanel({ record, onClose, onRecordChanged }: InfoPanelProps) {
  const state = stateFromLegacy(record);
  const flags = orderFlags(flagsFromLegacy(record));

  // Lifecycle actions — each gated strictly on the current state; a state
  // where none applies renders no Actions section at all. Every state that
  // can't Approve gets the Change state escape hatch (server still validates
  // each transition); PUBLISHED/AS_ACCEPTED keep their dedicated buttons too.
  const canApprove = APPROVABLE_STATES.includes(state);
  const canMarkAccepted = state === "PUBLISHED";
  const canUndoAccepted = state === "AS_ACCEPTED";
  const canChangeState = !canApprove;
  const showActions = canApprove || canMarkAccepted || canUndoAccepted || canChangeState;

  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // Two-step guard for the destructive Reject (PromptCard's arm → "Sure?"
  // pattern, with the same timeout so a missed click doesn't stay armed).
  const [rejectArmed, setRejectArmed] = useState(false);
  // Change state picker: the state chosen but not yet confirmed.
  const [targetState, setTargetState] = useState<ImageLifecycleState | null>(null);

  // Navigating to another record must not inherit the previous one's
  // pending/error/arm (same id after a reload — state is already clean then).
  useEffect(() => {
    setActionError(null);
    setActionPending(false);
    setRejectArmed(false);
    setTargetState(null);
  }, [record.id]);

  useEffect(() => {
    if (!rejectArmed) return;
    const timer = setTimeout(() => setRejectArmed(false), 4000);
    return () => clearTimeout(timer);
  }, [rejectArmed]);

  /** One lifecycle call: pending while in flight, backend `detail` inline on failure. */
  const runStateAction = useCallback(
    async (action: () => Promise<unknown>) => {
      setActionPending(true);
      setActionError(null);
      try {
        await action();
        onRecordChanged?.();
      } catch (err) {
        setActionError(err instanceof Error ? err.message : String(err));
      } finally {
        setActionPending(false);
      }
    },
    [onRecordChanged]
  );

  const hasMetadata =
    Boolean(record.generated_title) ||
    Boolean(record.generated_description) ||
    (record.generated_keywords?.length ?? 0) > 0 ||
    record.category != null ||
    Boolean(record.suggested_filename);

  const hasQc =
    record.acceptance_score != null ||
    !isEmptyValue(record.acceptance_report) ||
    record.semantic_confidence_score != null ||
    (record.semantic_flags?.length ?? 0) > 0 ||
    record.laplacian_variance != null ||
    Boolean(record.ocr_text_detected) ||
    record.ocr_text_content != null;

  const ocrSnippet =
    record.ocr_text_content && record.ocr_text_content.length > 200
      ? `${record.ocr_text_content.slice(0, 200)}…`
      : record.ocr_text_content;

  const batch = shortId(record.batch_id);
  const group = shortId(record.group_id);
  const prompt = shortId(record.prompt_id);

  return (
    <div className="flex h-full flex-col">
      {/* Sticky header so the close control survives scrolling. */}
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-parchment-500/30 bg-ink-900 px-4 py-2.5">
        <p className="label-caps">Image details</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close info panel"
          className="inline-flex h-7 w-7 items-center justify-center rounded-sm border border-parchment-500/50 font-stamp text-[11px] text-ink-50 hover:bg-parchment-50/20"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 divide-y divide-dashed divide-parchment-400/60">
        {showActions && (
          <Section title="Actions">
            <div className="flex flex-wrap items-center gap-2">
              {canApprove && (
                <Button
                  size="sm"
                  loading={actionPending}
                  disabled={actionPending}
                  onClick={() => void runStateAction(() => approveRecord(record.id))}
                >
                  Approve
                </Button>
              )}
              {state === "APPROVED" && (
                <Button
                  size="sm"
                  variant="danger"
                  loading={actionPending}
                  disabled={actionPending}
                  onClick={() => {
                    if (!rejectArmed) {
                      setRejectArmed(true);
                      return;
                    }
                    setRejectArmed(false);
                    void runStateAction(() => changeRecordState(record.id, "REJECTED"));
                  }}
                >
                  {rejectArmed ? "Sure?" : "Reject"}
                </Button>
              )}
              {canMarkAccepted && (
                <Button
                  size="sm"
                  loading={actionPending}
                  disabled={actionPending}
                  onClick={() =>
                    void runStateAction(() => changeRecordState(record.id, "AS_ACCEPTED"))
                  }
                >
                  Mark AS accepted
                </Button>
              )}
              {canUndoAccepted && (
                <Button
                  size="sm"
                  variant="secondary"
                  loading={actionPending}
                  disabled={actionPending}
                  onClick={() =>
                    void runStateAction(() => changeRecordState(record.id, "PUBLISHED"))
                  }
                >
                  Undo accepted
                </Button>
              )}
              {canChangeState && (
                <span className="flex flex-wrap items-center gap-2">
                  <label
                    htmlFor="change-state"
                    className="label-caps text-ink-400"
                  >
                    Change state
                  </label>
                  <select
                    id="change-state"
                    className="rounded-sm border border-parchment-500/50 bg-ink-900 px-2 py-1.5 text-xs text-ink-50 focus:border-brass-400 focus:outline-none focus:ring-1 focus:ring-brass-400"
                    value={targetState ?? state}
                    disabled={actionPending}
                    onChange={(event) => {
                      const next = event.target.value as ImageLifecycleState;
                      setTargetState(next === state ? null : next);
                    }}
                  >
                    {LIFECYCLE_STATES.map((option) => (
                      <option key={option} value={option}>
                        {STATE_LABELS[option]}
                      </option>
                    ))}
                  </select>
                  {targetState && (
                    <>
                      <Button
                        size="sm"
                        loading={actionPending}
                        disabled={actionPending}
                        onClick={() => {
                          const next = targetState;
                          setTargetState(null);
                          void runStateAction(() => changeRecordState(record.id, next));
                        }}
                      >
                        Change
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={actionPending}
                        onClick={() => setTargetState(null)}
                      >
                        Cancel
                      </Button>
                    </>
                  )}
                </span>
              )}
            </div>
            {actionError && (
              <p
                className="mt-2 rounded-sm border border-oxblood-500/40 bg-oxblood-400/10 px-2.5 py-1.5 text-[11px] text-oxblood-400"
                role="alert"
              >
                {actionError}
              </p>
            )}
          </Section>
        )}

        {hasMetadata && (
          <Section title="Metadata">
            <Row label="Title" value={record.generated_title} wrap />
            {record.generated_description && (
              <p className="whitespace-pre-wrap break-words py-1 text-xs leading-relaxed text-ink-200">
                {record.generated_description}
              </p>
            )}
            {(record.generated_keywords?.length ?? 0) > 0 && (
              <div className="py-1">
                <p className="label-caps mb-0.5">
                  Keywords · {record.generated_keywords!.length}
                </p>
                <Chips items={record.generated_keywords!} />
              </div>
            )}
            <Row
              label="Category"
              value={record.category ?? "—"}
              title={
                record.category != null
                  ? `Adobe category code ${record.category}`
                  : undefined
              }
            />
            <Row label="Suggested file" value={record.suggested_filename} mono wrap />
          </Section>
        )}

        <Section title="Status & pipeline">
          {record.status && (
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <Badge tone={STATUS_TONES[record.status] ?? "neutral"}>
                {record.status}
              </Badge>
            </div>
          )}
          <BadgeRow label="State">
            <Badge tone={stateTone(state)}>{stateLabel(state)}</Badge>
          </BadgeRow>
          {/* One chip per flag, contract display order — USED/UNUSED is always
              present, so this row never renders empty. */}
          <BadgeRow label="Flags">
            {flags.map((flag) => (
              <Badge key={flag} tone={flagTone(flag)}>
                {flagLabel(flag)}
              </Badge>
            ))}
          </BadgeRow>
          {/* Stage stays as pipeline telemetry, demoted to mono/secondary now
              that the lifecycle state above is the headline fact. */}
          <Row label="Stage" value={stageLabel(record.stage)} mono />
          <Row
            label="Queued stage"
            value={record.queued_stage ? stageLabel(record.queued_stage) : null}
          />
          <Row label="Stage updated" value={formatDate(record.stage_updated_at)} wrap />
          <Row label="Refine passes" value={record.refine_passes ?? 0} />
          <Row label="Created" value={formatDate(record.created_at)} wrap />
          <Row label="Updated" value={formatDate(record.updated_at)} wrap />
          {!isEmptyValue(record.stage_details) && (
            <div className="pt-1.5">
              <p className="label-caps mb-0.5">Stage details</p>
              <JsonRows data={record.stage_details!} />
            </div>
          )}
        </Section>

        {hasQc && (
          <Section title="Compatibility / QC">
            <Row
              label="Acceptance"
              value={
                record.acceptance_score != null
                  ? `${(record.acceptance_score * 100).toFixed(0)}%`
                  : "—"
              }
              title={
                record.acceptance_score != null
                  ? `acceptance_score = ${record.acceptance_score}`
                  : undefined
              }
            />
            <Row
              label="Semantic confidence"
              value={
                record.semantic_confidence_score != null
                  ? `${(record.semantic_confidence_score * 100).toFixed(0)}%`
                  : null
              }
            />
            <Row
              label="Laplacian var."
              value={
                record.laplacian_variance != null
                  ? record.laplacian_variance.toFixed(2)
                  : null
              }
              title={
                record.laplacian_variance != null
                  ? `laplacian_variance = ${record.laplacian_variance}`
                  : undefined
              }
            />
            <Row
              label="OCR text"
              value={record.ocr_text_detected == null ? null : record.ocr_text_detected ? "Detected" : "Clear"}
            />
            {(record.semantic_flags?.length ?? 0) > 0 && (
              <div className="py-1.5">
                <p className="label-caps mb-1">Semantic flags</p>
                <Chips
                  items={record.semantic_flags!}
                  tone="border-rust-400/60 bg-rust-400/10 text-rust-400"
                />
              </div>
            )}
            {ocrSnippet && (
              <div className="py-1.5">
                <p className="label-caps mb-1">OCR snippet</p>
                <p
                  className="max-h-28 overflow-y-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-ink-400"
                  title={record.ocr_text_content ?? undefined}
                >
                  {ocrSnippet}
                </p>
              </div>
            )}
            {!isEmptyValue(record.acceptance_report) && (
              <div className="pt-1.5">
                <p className="label-caps mb-0.5">Acceptance report</p>
                <JsonRows data={record.acceptance_report!} />
              </div>
            )}
          </Section>
        )}

        <Section title="Names">
          <Row label="Original file" value={record.filename} wrap />
          {record.upload_filename && (
            <div className="py-0.5">
              <div className="flex items-baseline justify-between gap-3">
                <span className="label-caps shrink-0 text-brass-300">
                  Upload · ships
                </span>
                <span
                  className="min-w-0 truncate text-right font-stamp text-[11px] text-brass-300"
                  title={record.upload_filename}
                >
                  {record.upload_filename}
                </span>
              </div>
              <p className="text-[10px] text-ink-400">
                What Adobe receives (CSV Filename column).
              </p>
            </div>
          )}
          <Row label="Download name" value={record.download_name} mono wrap />
          <Row label="Suggested" value={record.suggested_filename} mono wrap />
        </Section>

        <Section title="Technical">
          <Row
            label="Dimensions"
            value={
              record.width != null && record.height != null
                ? `${record.width} × ${record.height}`
                : "—"
            }
          />
          <Row
            label="Megapixels"
            value={record.megapixels != null ? `${record.megapixels.toFixed(1)} MP` : "—"}
          />
          <Row label="File size" value={formatFileSize(record.file_size_bytes) ?? "—"} />
          <Row
            label="Original path"
            value={record.original_path ?? null}
            mono
            wrap
            title={record.original_path ?? undefined}
          />
          <Row
            label="Working path"
            value={record.working_path ?? null}
            mono
            wrap
            title={record.working_path ?? undefined}
          />
          <Row label="Batch" value={batch?.value ?? null} mono title={batch?.title} />
          <Row label="Folder" value={group?.value ?? null} mono title={group?.title} />
          <Row label="Prompt" value={prompt?.value ?? null} mono title={prompt?.title} />
          <Row label="Used" value={record.is_used ? "Yes" : "No"} />
          <Row label="Used at" value={formatDate(record.used_at)} wrap />
        </Section>
      </div>
    </div>
  );
}
