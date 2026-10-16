/**
 * Single source of truth for the record lifecycle vocabulary.
 *
 * Every UI surface (gallery filters, tiles, viewer, home cards) reads its
 * labels, badge tones and flag ordering from here so the wire contract
 * (`state` + `flags`, uppercase, exact strings) never leaks raw into markup.
 * Legacy fallbacks cover responses that predate the new fields.
 */
import type { BadgeTone } from "@/components/ui/Badge";
import type { ImageLifecycleState, ImageRecord } from "./types";

/** Lifecycle states in contract order. */
export const LIFECYCLE_STATES = [
  "COLLECTED",
  "APPROVED",
  "REJECTED",
  "READY_TO_PUBLISH",
  "PUBLISHED",
  "AS_ACCEPTED",
] as const satisfies readonly ImageLifecycleState[];

/** Flags in contract display order (exactly one of USED/UNUSED is always present). */
export const FLAG_ORDER = [
  "QUARANTINED",
  "USED",
  "UNUSED",
  "METADATA_READY",
  "INCOMPATIBLE",
  "REFINED",
  "UPSCALED",
  "OCR_REJECTED",
] as const;

export type ImageFlag = (typeof FLAG_ORDER)[number];

export const STATE_LABELS: Record<ImageLifecycleState, string> = {
  COLLECTED: "Collected",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  READY_TO_PUBLISH: "Ready to publish",
  PUBLISHED: "Published",
  AS_ACCEPTED: "AS Accepted",
};

export const STATE_TONES: Record<ImageLifecycleState, BadgeTone> = {
  COLLECTED: "neutral",
  APPROVED: "success",
  REJECTED: "danger",
  READY_TO_PUBLISH: "info",
  PUBLISHED: "success",
  AS_ACCEPTED: "success",
};

export const FLAG_LABELS: Record<ImageFlag, string> = {
  QUARANTINED: "Quarantined",
  USED: "Used",
  UNUSED: "Unused",
  METADATA_READY: "Metadata ready",
  INCOMPATIBLE: "Incompatible",
  REFINED: "Refined",
  UPSCALED: "Upscaled",
  OCR_REJECTED: "OCR rejected",
};

export const FLAG_TONES: Record<ImageFlag, BadgeTone> = {
  QUARANTINED: "warn",
  USED: "info",
  UNUSED: "neutral",
  METADATA_READY: "success",
  INCOMPATIBLE: "danger",
  REFINED: "neutral",
  UPSCALED: "neutral",
  OCR_REJECTED: "danger",
};

/** States from which the detail panel's Approve action may run (fast flip). */
export const APPROVABLE_STATES: readonly ImageLifecycleState[] = [
  "APPROVED",
  "REJECTED",
];

/** Display label for a state; unknown values fall back to the raw wire form. */
export function stateLabel(state: ImageLifecycleState | string): string {
  return (
    STATE_LABELS[state as ImageLifecycleState] ?? String(state).replace(/_/g, " ")
  );
}

/** Badge tone for a state; unknown values render neutral. */
export function stateTone(state: ImageLifecycleState | string): BadgeTone {
  return STATE_TONES[state as ImageLifecycleState] ?? "neutral";
}

/** Display label for a flag; unknown flags fall back to the raw wire form. */
export function flagLabel(flag: string): string {
  return FLAG_LABELS[flag as ImageFlag] ?? flag.replace(/_/g, " ");
}

/** Badge tone for a flag; unknown flags render neutral. */
export function flagTone(flag: string): BadgeTone {
  return FLAG_TONES[flag as ImageFlag] ?? "neutral";
}

/** Sort flags into contract display order (unknown flags keep input order, last). */
export function orderFlags(flags: readonly string[]): string[] {
  return [...flags].sort((a, b) => {
    const ia = FLAG_ORDER.indexOf(a as ImageFlag);
    const ib = FLAG_ORDER.indexOf(b as ImageFlag);
    if (ia === -1 && ib === -1) return 0;
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

/**
 * Lifecycle state for responses that predate the `state` field: derive it
 * from the legacy `stage`/`status` pair. Order follows the contract mapping
 * (stage PUBLISHED → status READY → rejections → METADATA_READY → collected).
 */
export function stateFromLegacy(
  record: Pick<ImageRecord, "state" | "stage" | "status">
): ImageLifecycleState {
  if (record.state) return record.state;
  if (record.stage === "PUBLISHED") return "PUBLISHED";
  if (record.status === "READY") return "READY_TO_PUBLISH";
  if (
    record.status === "FLAGGED" ||
    record.stage === "OCR_REJECTED" ||
    record.stage === "INCOMPATIBLE" ||
    record.stage === "QUARANTINED"
  ) {
    return "REJECTED";
  }
  if (record.stage === "METADATA_READY") return "APPROVED";
  return "COLLECTED";
}

/**
 * Flags for responses that predate the `flags` field: usage is the only
 * derivable fact (`is_used`), everything else starts empty.
 */
export function flagsFromLegacy(
  record: Pick<ImageRecord, "flags" | "is_used">
): string[] {
  if (record.flags) return record.flags;
  return record.is_used ? ["USED"] : ["UNUSED"];
}
