# 46 — API Schemas, Validation, and Pagination

## Purpose
Specify typed wire schemas that keep frontend behavior, backend validation, and persistence boundaries consistent for large batches and partial failures.

## Scope
This document covers request and response fields, nullability, enums, validation, filtering, sorting, pagination, error details, and compatibility. It does not define route ownership, sessions, or security policy.

## Decisions / requirements
API schemas are distinct from ORM models and internal provider envelopes. Responses use stable identifiers, timestamps with explicit timezone semantics, aggregate status, blocker summaries, and bounded evidence. Absolute source paths, credentials, raw prompts, and unbounded logs are never serialized. Optional fields are explicitly nullable rather than omitted unpredictably when clients need to distinguish “not evaluated” from “empty.”

Upload requests validate count, filename metadata, declared content type, and per-file limits while the server remains authoritative after decoding. Batch responses include accepted, duplicate, invalid, and deferred items independently. Action requests include an expected revision, optional reason code and note, and an idempotency key where required. Metadata requests distinguish generated, edited, and approved versions and validate title and keyword constraints before persistence.

Collection endpoints support stable filters for status, batch, technical outcome, semantic risk, provider state, approval state, and export state. Sorting fields are allow-listed and have deterministic tie-breakers, typically identifier after timestamp. Cursor pagination is preferred for changing review queues; if offset pagination is used for MVP, the response must include a snapshot or clear consistency semantics. Page sizes are bounded and server-controlled.

Error details identify a field, item identifier, or blocker code without echoing unsafe content. Schema evolution is additive where possible. Enum expansion must not cause clients to treat unknown states as ready. Date, decimal, confidence, and hash formats are documented and validated at both boundaries.

## Affected blueprint areas
This governs the Pydantic payload layer, records listing, upload response, approval actions, metadata editing, job progress, and Next.js client types.

## Dependencies
It depends on documents 14–20, 21, 27, 34–46, and the frontend requirements. Canonical state names and title/keyword policies must be resolved before schema freeze.

## Acceptance criteria
- Wire schemas are typed independently from database models.
- Nullability distinguishes absent, pending, failed, and empty values.
- Batch responses preserve per-item outcomes.
- Pagination, sorting, filters, and page limits are deterministic and bounded.
- Errors are machine-readable, safe, and actionable.
- Additive evolution rules prevent unknown states from being misread as success.

## Risks / open questions
Cursor pagination adds implementation complexity but avoids duplicate or missing records during live processing. Large evidence payloads may slow the UI. The team must decide the canonical identifier format, whether confidence is decimal or integer percentage on the wire, and which fields are searchable.