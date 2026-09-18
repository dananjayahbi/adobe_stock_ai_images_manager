# 12 — Error Taxonomy and Recovery Strategy

## Purpose
Provide consistent classifications and recovery behavior for validation, processing, provider, storage, database, and user-action failures. Clear error semantics prevent silent loss and keep retry operations safe.

## Scope
The taxonomy covers malformed uploads, unsupported images, path violations, duplicate content, QC failures, OCR/tool failures, AI authentication and rate limits, malformed AI responses, metadata errors, ExifTool failures, filesystem conflicts, database conflicts, cancellation, and restart recovery. It includes API and UI presentation but not a complete logging schema.

## Decisions and requirements
Errors are classified as user-correctable, retryable, blocked-by-dependency, terminal-for-asset, or internal-investigation. A hard QC failure is a valid business outcome, not an infrastructure error. Provider rate limits and temporary network failures are retryable with bounded backoff; invalid credentials require configuration correction; malformed model output is provider-response failure and must never become trusted metadata.

Every failure includes a stable category, safe user message, diagnostic detail reference, stage, attempt number, correlation identifier, and suggested action. Sensitive values and raw credentials are excluded. Retry operations are stage-specific and idempotent. A failed metadata embed leaves the source and prior evidence intact and does not mark the item READY. Cancellation is cooperative and results in a distinguishable cancelled state or job outcome.

On restart, durable jobs are recovered or marked for reconciliation. Missing source files, mismatched hashes, and database/file disagreement require explicit repair, not automatic recreation. The UI should show partial batch results and distinguish “not attempted” from “failed.”

## Affected blueprint areas
This plan governs background auditing, upload and approval endpoints, Gemini and ExifTool services, database operations, filesystem lifecycle, dashboard status badges, health diagnostics, and operations support. It feeds documents 02, 07, 10–13, 21–26, 33–44, and 45–66.

## Dependencies
The taxonomy depends on the status machine, job model, API error envelope, logging and audit-event design, provider retry policy, and filesystem reconciliation strategy. It also requires security review of messages and diagnostic bundles.

## Acceptance criteria
- Every expected failure has a stable class and recovery action.
- Retryable failures use bounded attempts and do not duplicate outputs or provider work unnecessarily.
- Terminal asset failures remain inspectable and do not destroy originals.
- API responses and UI messages are safe, actionable, and consistent.
- Restart and partial-batch behavior are tested.
- Operational logs correlate failures without exposing secrets or raw sensitive content.

## Risks and open questions
Overly broad retries can increase Gemini cost or worsen rate limiting. Overly broad terminal states can strand recoverable work. The owner must define retry budgets, user-visible attempt limits, cancellation semantics, and whether a failed dependency blocks the entire batch or only affected items. Some native-library failures may be difficult to classify reliably.