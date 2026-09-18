# 17 — Database Schema and Index Plan

## Purpose
Plan durable SQLite structures that support lifecycle queries, auditability, idempotency, and recovery without making JSON blobs the only source of truth.

## Scope
The plan covers logical tables, relationships, constraints, indexes, and bounded JSON use for assets, batches, files, audits, findings, decisions, jobs, events, and exports. It excludes migration execution and ORM-specific syntax.

## Decisions / requirements
The database should separate asset identity from source-file identity. Core tables are batches, assets, files, qc_audits, qc_findings, metadata_revisions, review_decisions, jobs, state_events, and exports. A file row records role, relative path, hash, byte size, media facts, and lifecycle. An audit belongs to an asset and policy version and has an immutable result; findings belong to the audit with rule, severity, observed value, explanation, and evidence reference.

Foreign keys are required, deletion behavior is conservative, and historical evidence is retained even when an asset is rejected. Current pointers may be stored on assets for efficient reads but must reference valid related rows. Unique constraints include content hash plus relevant representation, audit identity plus execution, metadata revision number per asset, and export manifest identity. Display filenames remain non-unique.

Indexes prioritize status and updated time for review queues; batch and status for batch pages; source hash for deduplication; job state and next-attempt time for workers; asset and created time for event history; severity and unresolved state for review filters; and export state for ready-pool reconciliation. Indexes must not expose secrets or raw OCR text. Detector-specific details may use bounded JSON with a schema version, while rule identifiers, severities, and observed scalar values remain columns.

Transactions must cover database changes that establish references, but filesystem operations follow the atomic workflow in document 26. The design must tolerate a file existing before its final database commit and must provide reconciliation markers rather than assuming transactional filesystem semantics. Soft deletion or archival is preferred to cascading deletion for sources and evidence.

## Affected blueprint areas
This expands the blueprint SQLite engine and image record into a relational persistence boundary used by API, workers, storage, review, diagnostics, and export.

## Dependencies
It depends on documents 14–16 for entities and states, 19 for uniqueness and hashes, 20 for retention, 25–26 for jobs and files, and 27 for QC evidence.

## Acceptance criteria
- Each table has a clear owner, key, relationship, and retention behavior.
- Queries for pending review, failed jobs, duplicates, and ready exports are indexed.
- Historical audits and decisions remain queryable after new revisions.
- Constraints prevent dangling references and duplicate active exports.
- JSON fields are bounded, versioned, and not used for mandatory workflow predicates.

## Risks / open questions
SQLite concurrency may limit simultaneous workers and review actions. The team must confirm expected batch volume, whether full-text search is needed, and whether event history should be append-only in a dedicated table or supplemented by audit logs. Migration details belong in document 18.