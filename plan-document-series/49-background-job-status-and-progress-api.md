# 49 — Background Job Status and Progress API

## Purpose
Give the frontend and operator a trustworthy view of batch and item progress across upload, QC, AI calls, metadata, verification, export, retry, and cancellation.

## Scope
This document covers job resources, progress stages, counters, per-item status, polling and push choices, cancellation, errors, and restart recovery. It does not prescribe frontend visual design or worker implementation details.

## Decisions / requirements
Every asynchronous operation creates a durable job with stable identifier, operation type, parent batch or item references, lifecycle status, creation and update timestamps, progress counters, current stage, attempt information, and safe error summary. Stages include queued, intake, deterministic QC, semantic audit, metadata, review-waiting, embedding, verification, export, completed, failed, cancelled, and partially completed. A job may expose a coarse percentage, but counters and stage are authoritative because work durations differ.

Batch progress reports total, completed, active, queued, failed, blocked, cancelled, and skipped counts. Item progress identifies the current aggregate state and the job or blocker responsible without exposing worker internals. A failed item does not stop unrelated items unless the failure is a batch-wide invariant. The API distinguishes “waiting for human review” from “worker stalled.”

Polling is the MVP transport with bounded intervals and conditional requests or revision numbers to reduce load. A future server-sent event or WebSocket channel may be added without changing the job resource. Poll responses are safe to repeat and return the latest durable snapshot. The frontend must handle out-of-order responses and terminal jobs without continuing aggressive polling.

Cancellation is an explicit action that marks a request and returns accepted status; workers stop at safe boundaries and report cancelled or cancellation-failed. Restart recovery identifies expired leases and resumes or fails jobs according to stage policy. Progress events are append-only or sequence-numbered when detailed history is needed, while the current job row remains compact.

## Affected blueprint areas
This replaces ad hoc three-second record polling and BackgroundTasks-only visibility with a durable progress contract for upload, audit, approval, packaging, and export.

## Dependencies
It depends on documents 12, 16, 21, 25, 26, 44, and 45–48. Worker leases, cancellation semantics, and frontend polling limits must be agreed before implementation.

## Acceptance criteria
- Every asynchronous action has a durable, queryable job.
- Stage, counters, blockers, and terminal outcomes are distinguishable.
- Partial batches report item-level failures and successes.
- Cancellation and restart recovery are visible and deterministic.
- Polling is bounded, revision-aware, and safe under stale responses.
- No progress response exposes secrets, absolute paths, or raw provider data.

## Risks / open questions
Percentage progress may mislead when AI latency varies or items are retried. Push transport could add complexity for a local app. The owner must decide default polling intervals, lease recovery policy, whether progress events are retained, and how a job behaves when a human review pause lasts for days.