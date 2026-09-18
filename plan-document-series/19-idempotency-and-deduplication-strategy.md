# 19 — Idempotency and Deduplication Strategy

## Purpose
Prevent repeated uploads, retries, worker restarts, and repeated approval actions from producing duplicate records, charges, files, or exports.

## Scope
The strategy covers content identity, upload retries, filenames, processing commands, provider calls, metadata revisions, and ready-pool exports. It does not define general database migration or external marketplace submission behavior.

## Decisions / requirements
Content identity is based on a cryptographic hash of the safely stored source bytes, supplemented by byte size and media facts for diagnostics. The hash is calculated after complete upload and before processing. Original filenames are display metadata and may collide. A duplicate hash should return the existing asset or a clearly linked duplicate outcome according to user-selected behavior; it must never overwrite the original or silently merge unrelated batch history.

Every client command that can be retried carries an idempotency key scoped to the operation and actor or batch. The server stores the key, request fingerprint, result, and expiry policy. Repeating the same command returns the original result; reusing a key for different input fails safely. Worker jobs use an asset, stage, input hash, policy version, and attempt identity to detect stale or repeated execution.

Provider requests require a separate strategy because a network timeout does not reveal whether a request was accepted. Where supported, provider calls include a stable request correlation and cache key. Results are stored with model, prompt, input hash, and policy provenance. If safe deduplication cannot be guaranteed, retries require a visible uncertainty state and may need human confirmation rather than blind repetition.

Metadata generation creates a new revision only when output differs or a deliberate retry is requested. Packaging writes a deterministic output identity from source hash, approved metadata revision, policy version, and packaging configuration. Repeating a completed export returns the existing verified artifact. If bytes differ, the old export remains historical and the new artifact receives a new identity.

## Affected blueprint areas
This affects upload endpoints, batch ingestion, database uniqueness, background jobs, Gemini integration, ExifTool packaging, ready staging, and UI retry actions. It is required by documents 14–18, 21, 25–26, 33–39, and 43–44.

## Dependencies
The plan depends on content-addressed files, durable jobs, state transitions, provider provenance, and atomic filesystem operations. It also requires defined expiration for request idempotency records.

## Acceptance criteria
- Repeated upload of identical bytes never creates an unlinked duplicate.
- Retrying a stage does not duplicate findings, metadata revisions, or exports unintentionally.
- Repeated approval and packaging actions are safe and observable.
- Filename collisions are deterministic and non-destructive.
- Provider uncertainty is represented rather than falsely treated as failure or success.
- Hash and identity evidence is visible in diagnostics.

## Risks / open questions
Near-duplicate images with different bytes need a product decision: warn, allow, or add perceptual similarity later. Hashing large files consumes time and storage I/O. Provider support for idempotency is uncertain. The retention duration for idempotency keys and cached AI results must balance recovery with privacy and cost.