# 45 — REST API Resource and Route Contract

## Purpose
Define stable REST resources and route responsibilities for local upload, review, audit, approval, metadata, jobs, export, and health operations without leaking internal implementation details.

## Scope
The contract covers resource identity, route families, HTTP methods, normal outcomes, action semantics, and broad authorization boundaries. Field-level schemas and pagination are defined in document 46; concurrency and security are defined in documents 47 and 48.

## Decisions / requirements
The API is versioned under a stable prefix and exposes resources for batches, image records, audits, metadata versions, review decisions, jobs, exports, and health. Collection routes support listing and filtering; item routes return current aggregate state and links or identifiers for related evidence. Upload is a multipart batch creation operation with per-file results. It must not accept arbitrary server paths.

Actions such as retry audit, request metadata, approve, reject, override, re-audit, cancel, and finalize are explicit POST operations because they create auditable events and may enqueue jobs. They return an accepted job representation when work is asynchronous, or a completed result when a safe synchronous operation is guaranteed. Idempotency keys are required for externally repeatable mutating actions where duplicate clicks could cause work or state changes.

Review routes expose bounded technical findings, semantic findings, metadata proposals, blockers, and history while omitting secrets and absolute filesystem paths. Export routes create or inspect a package and return manifest summaries, not arbitrary directory access. Health has separate liveness and dependency readiness views so a missing Gemini credential does not make deterministic review appear unavailable.

Errors use a consistent envelope with machine-readable type, stable code, human-safe message, correlation identifier, and field or item details where appropriate. The API distinguishes validation failure, not found, conflict, forbidden, rate-limited, unavailable, and internal failure. It does not return provider stack traces or raw ExifTool commands.

## Affected blueprint areas
This formalizes the blueprint’s upload, records, approval, background audit, thumbnail, and ready-pool endpoints and establishes the contract consumed by the Next.js client.

## Dependencies
It depends on documents 12, 14–20, 21, 24–26, 33–44, and 46–49. Route names and status codes must be reviewed against the frontend information architecture before implementation.

## Acceptance criteria
- Every supported user operation has one documented route and resource response.
- Mutating actions are auditable and idempotency-aware.
- Asynchronous operations return durable job identity and current aggregate state.
- Responses never expose local paths, secrets, or unbounded provider data.
- Error envelopes are consistent across validation, conflict, provider, and storage failures.
- Health distinguishes core service liveness from optional provider readiness.

## Risks / open questions
Route naming may evolve as the domain model becomes more detailed. A local API exposed beyond localhost creates security obligations. The owner must decide whether API versioning begins at `/api/v1`, whether thumbnails use a separate protected route, and which actions are allowed in batch form.