# 44 — Approval and Finalization State Machine

## Purpose
Define the authoritative transitions from review decision to metadata finalization and READY so approval cannot be confused with successful packaging and every failure has a recoverable state.

## Scope
This document covers eligibility, approval events, metadata generation, manual metadata edits, embedding, verification, retries, cancellation, stale results, and terminal or reversible states. It complements the general state machine in document 16.

## Decisions / requirements
Approval is a human decision that records the reviewer, evidence versions, source hash, and policy version. It moves an eligible item into an approved or finalization-pending state, not directly to READY. Finalization then obtains or selects metadata, validates it, embeds it into a derived copy, verifies the output, creates the manifest entry, and atomically commits READY.

An item with hard technical failure, unresolved high-risk semantic finding, missing required evidence, stale audit, missing disclosure acknowledgment, or invalid metadata cannot enter finalization. A warning may proceed only with a recorded override where policy permits. Provider failure, malformed output, ExifTool failure, verification mismatch, collision, and filesystem interruption produce distinct finalization-failed outcomes that preserve the human approval while allowing stage-specific retry. A source or approved metadata change invalidates the pending operation.

Transitions use optimistic revision checks and durable job ownership. Completion is idempotent: if the same export identity is already verified and registered, repeating the request returns the existing result. A cancelled finalization cannot later commit READY. Rejection or withdrawal after approval invalidates uncommitted output; an existing ready artifact is marked stale and removed or quarantined according to lifecycle policy, never silently left as current.

The state machine exposes separate item status, approval status, metadata status, packaging status, and job status where one field would create ambiguity. Public APIs provide a simplified aggregate status plus detailed blockers. Every transition emits an audit event.

## Affected blueprint areas
This replaces the blueprint’s direct `APPROVED -> READY` assumption with explicit finalization phases and governs endpoints, workers, metadata, ExifTool, exports, and progress reporting.

## Dependencies
It depends on documents 05, 12, 14–20, 25–26, 34–44, and API concurrency rules. Product and policy owners must approve disclosure acknowledgment and override eligibility.

## Acceptance criteria
- READY requires human approval, current evidence, valid metadata, verified embedding, and manifest registration.
- Each failure maps to a visible, retryable, or terminal state.
- Repeated finalization is idempotent.
- Stale or cancelled work cannot commit a current READY result.
- Approval and packaging histories remain separately attributable.
- API clients can identify blockers without reading internal paths.

## Risks / open questions
A richer state model may complicate existing UI assumptions and migrations. Deleting stale ready outputs could surprise users who already copied them. The owner must define exact state names, whether approval may be withdrawn after READY, and whether a failed provider call preserves approval indefinitely.