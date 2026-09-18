# 15 — Image Record Schema

## Purpose
Define the typed image record contract that replaces the blueprint’s minimal, loosely typed record. The schema must support review, provenance, processing recovery, and historical interpretation without hiding important null or failure states.

## Scope
This document covers the asset-facing record and its relationships to files, audits, metadata, decisions, jobs, and exports. It does not prescribe SQL table layout, migration mechanics, or REST serialization details.

## Decisions / requirements
The primary record requires an opaque identifier, batch reference, lifecycle status, display filename, source-file reference, source content hash, and created and updated timestamps. Filename is descriptive only and cannot be unique by itself. Source dimensions, megapixels, media type, byte size, color information, and orientation are captured as observed facts with an observation timestamp; they are not silently recomputed in a later state.

The record exposes current pointers to the active technical audit, semantic audit, metadata revision, human decision, and export. Historical rows remain available through related collections. Pointers may be null while work is incomplete, and null must not be interpreted as pass. A structured readiness summary may be materialized for queries, but the authoritative evidence remains in immutable audit and decision records.

Failure information uses a typed code, stage, retryability, message safe for display, and diagnostic reference. Secrets, provider credentials, raw prompts containing sensitive data, and unbounded OCR text do not belong in the main image record. Large evidence is stored as bounded, content-addressed artifacts with metadata references. JSON is permitted for detector-specific details and forward-compatible evidence, but required business fields remain typed and queryable.

The schema must distinguish original filename from stored relative path, normalized derivative path, thumbnail path, quarantine path, and ready export path. Paths are storage-relative identifiers, never arbitrary user-supplied absolute paths. Hash algorithms and policy versions are explicit. Timestamps use UTC and retain event ordering information sufficient for audit reconstruction.

## Affected blueprint areas
This updates the blueprint’s `ImageRecord` concept, SQLite model, API payloads, dashboard cards, storage layout, and QC diagnostics. It informs documents 16–20, 27, 40–44, and 45–49.

## Dependencies
The schema depends on domain vocabulary from document 14, status rules from document 16, table design from document 17, content hashing from document 19, and retention rules from document 20.

## Acceptance criteria
- Required and nullable fields are documented with semantic meaning.
- No filename or path is treated as a durable identity.
- Current evidence pointers and historical evidence can coexist.
- Failure and retry data are queryable without parsing free text.
- Record contents are safe to expose through a least-privilege API projection.
- Historical records remain interpretable after policy or detector changes.

## Risks / open questions
The team must choose UUID or another opaque identifier format and decide whether hashes are stored on every derivative or only at export boundaries. OCR evidence may require separate encrypted or short-lived storage. The balance between normalized tables and JSON detector payloads needs confirmation after query requirements are known.