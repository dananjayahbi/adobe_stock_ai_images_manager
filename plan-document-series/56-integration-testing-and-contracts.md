# 56 — Integration Testing and Contracts

## Purpose
Verify that application components collaborate correctly across persistence, filesystem storage, job dispatch, API boundaries, and external-tool adapters without requiring a production environment.

## Scope
This document covers backend integration tests, API contract tests, SQLite migrations, storage lifecycle, job recovery, ExifTool and OCR adapters, frontend-backend schema compatibility, and provider adapter seams. It excludes full browser journeys and high-volume load tests.

## Decisions / requirements
Integration tests use a disposable database and isolated storage tree for every scenario or suite. They exercise real serialization, transactions, migrations, path resolution, file naming, checksums, and cleanup behavior. A representative upload creates a record, stores the original, creates derivatives, records job progress, and leaves consistent evidence after success or failure. Tests assert atomicity when a downstream step fails and verify that retry does not duplicate records or overwrite originals.

API contract tests validate status codes, error envelopes, nullability, enum handling, pagination, revision conflicts, idempotency behavior, and bounded response fields. Generated or shared types must be checked against the backend schema so a field renamed in one layer cannot silently become undefined in the client. Unknown future enum values must produce a safe attention-needed presentation rather than a ready state.

Migration tests apply every migration to an empty database and upgrade a fixture representing the previous supported release. They verify indexes, constraints, default values, event history, and preservation of source references. Job recovery tests simulate process interruption between durable checkpoints and confirm reconciliation chooses retry, terminal failure, or already-complete based on evidence rather than guessing.

Adapter tests run against controlled local substitutes or installed tools in a separately marked suite. ExifTool verification must inspect output metadata, not only process exit status. OCR integration tests cover missing executable, timeout, malformed image, and valid output. Gemini integration remains isolated behind a recorded or fake provider contract; live calls belong to the AI test plan and never run by default.

## Affected blueprint areas
This plan covers database and migration documents, file lifecycle, job dispatch, API routes and schemas, OCR, ExifTool, Gemini adapter boundaries, packaging, and frontend type consumption.

## Dependencies
It depends on stable schemas, migration policy, deterministic fixtures, supported Windows tool discovery, and durable job checkpoints. Test data must avoid copyrighted or sensitive personal material.

## Acceptance criteria
- Clean database migration and supported upgrade paths pass.
- Upload, retry, failure cleanup, and finalization preserve invariants.
- API responses and errors conform to the documented contract.
- Idempotency and revision conflicts are proven with repeated requests.
- Tool-unavailable and provider-unavailable cases are represented accurately.
- Contract failures block release before browser tests run.

## Risks / open questions
SQLite locking behavior can differ under concurrent Windows processes. The team must decide the supported upgrade window, whether contract schemas are generated or hand-maintained, and which native-tool tests run on every change versus a release lane. Test isolation must be monitored to prevent flaky residue.