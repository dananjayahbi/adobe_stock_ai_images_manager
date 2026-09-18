# 16 — Status Machine and Transition Rules

## Purpose
Specify legal asset transitions so UI actions, workers, retries, and recovery cannot create misleading lifecycle states. The machine separates business status from individual job status and preserves human accountability.

## Scope
The model covers intake, validation, auditing, review, approval, rejection, packaging, ready staging, cancellation, and terminal or recoverable failures. It does not define API route names or visual presentation.

## Decisions / requirements
The canonical asset states are PENDING, VALIDATING, QUEUED, AUDITING, REVIEW_REQUIRED, PASSED_FOR_REVIEW, REJECTED, APPROVED, FINALIZING, READY, and FAILED. A quarantined source is represented by a safety outcome and storage disposition, not by pretending the asset completed normal processing. Job states are separate: QUEUED, RUNNING, SUCCEEDED, FAILED_RETRYABLE, FAILED_TERMINAL, CANCEL_REQUESTED, and CANCELLED.

Every transition has a command, actor or system identity, precondition, resulting state, event, and reason. PENDING may move to VALIDATING only after durable intake registration. VALIDATING may move to QUEUED, REVIEW_REQUIRED, or FAILED. AUDITING can produce REVIEW_REQUIRED or PASSED_FOR_REVIEW, but never APPROVED. Only an eligible human decision can move an asset to APPROVED. APPROVED may enter FINALIZING only when required metadata and disclosure confirmations are complete. READY requires verified packaging and matching hashes.

Rejection is reversible through an explicit reopen or reprocess command; the previous rejection remains in history. A technical hard failure blocks approval unless a policy-controlled exception is recorded. Warnings do not block by themselves, but unresolved provider or evidence errors do. Cancellation prevents new work and allows an in-flight job to finish safely or report cancellation; it never deletes originals. A stale worker may not overwrite a newer transition, so commands must carry an expected version or equivalent concurrency token.

Retries return an item to the narrowest valid prior state and create a new job attempt. They do not erase findings. Any source, policy, or metadata revision change invalidates downstream approval and export eligibility. READY is not a permanent promise: changing the approved material moves the asset back to an appropriate review or finalization state.

## Affected blueprint areas
This formalizes the blueprint status comment, upload and approval endpoints, worker orchestration, ready pool, dashboard badges, and audit history. It is consumed by documents 02, 12, 14, 19, 25, 26, 44, and 49.

## Dependencies
The machine depends on typed entities, decision policy, durable jobs, optimistic concurrency, and filesystem reconciliation. It also needs a defined local actor identity.

## Acceptance criteria
- Every command lists valid source and destination states.
- No automated path reaches APPROVED or READY.
- Retry, cancel, reopen, and stale-worker behavior is explicit and testable.
- State history explains each transition and its evidence.
- Invalid transitions fail safely without mutating files or status.

## Risks / open questions
Whether VALIDATING and QUEUED should be visible to users is undecided. Batch-level states may be derived rather than authoritative. The owner must choose whether approval expires after policy changes and how long cancellation may wait for an external tool.