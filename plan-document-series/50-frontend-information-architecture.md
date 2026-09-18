# 50 — Frontend Information Architecture

## Purpose
Define the information architecture for the local Next.js review workspace so an operator can move from intake to a defensible ready-to-upload package without learning internal database states or filesystem paths. The structure must expose the decisions that matter first: what needs attention, why it needs attention, and what action is safe next.

## Scope
This document covers global navigation, dashboard regions, batch and image views, filters, detail inspection, review evidence, metadata editing, export status, and settings entry points. It does not specify visual styling, component implementation, backend routes, or direct Adobe submission.

## Decisions / requirements
The primary workspace is a queue-oriented dashboard rather than a file browser. Its first level contains Overview, Review Queue, Batches, Ready to Upload, and Diagnostics. Overview summarizes pending work, blocking failures, provider availability, recent activity, and actionable counts. Review Queue supports a dense grid or list with thumbnail, filename, lifecycle state, technical outcome, semantic risk, approval state, and next action. Filters must be shareable within the current local session and must not silently discard records when processing updates the queue.

Selecting an item opens an inspection route or modal with a stable URL. The inspection layout places the image and 100% zoom controls beside an evidence panel. Technical findings, semantic findings, provenance, metadata versions, reviewer decision, and history are separate sections with clear labels. Blocking findings appear before advisory findings. Actions are contextual: retry only when retryable, approve only when required evidence exists, reject with a reason, and re-audit when the source or policy version warrants it.

A batch page provides progress, per-file outcomes, aggregate blockers, retry controls, and export readiness. Ready to Upload is a package-oriented view showing verified files, manifest identity, metadata verification, and the date of finalization. Diagnostics is read-only for normal operators and exposes dependency health, queue state, recent failures, and correlation identifiers without secrets. Settings should contain thresholds, provider configuration status, storage locations expressed as friendly labels, and policy version information.

## Affected blueprint areas
This refines the Next.js page, ImageGrid, InspectionModal, StatsBar, upload flow, API resources, status machine, and operational diagnostics described in the blueprint and documents 02, 07, 13, 45, and 49.

## Dependencies
It depends on the canonical status and error enums, API pagination, thumbnail routes, review policy, metadata model, and local access controls. UX copy requires policy-sensitive wording from documents 03–06.

## Acceptance criteria
- Every MVP operation is reachable from a predictable primary location.
- A user can identify the next safe action from any item state.
- Detail views never require filesystem or database knowledge.
- Queue filters and pagination preserve deterministic results during processing.
- Ready packages show verification evidence before export.
- Responsive behavior remains usable at the minimum supported desktop window.

## Risks / open questions
A single dashboard may become overloaded as evidence grows. The team must decide whether batches and individual records have separate routes in MVP, whether navigation state survives restart, and which diagnostics are safe for nontechnical operators. Unknown future states must render as attention-needed rather than success.