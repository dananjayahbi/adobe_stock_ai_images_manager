# 14 — Domain Entities and Invariants

## Purpose
Define the business objects that connect uploaded images, processing evidence, human decisions, and export artifacts. This document establishes vocabulary and invariants before persistence or API implementation begins.

## Scope
The domain includes assets, batches, source files, derivatives, QC audits, findings, metadata sets, review decisions, processing jobs, and exports. It excludes UI component structure, provider-specific prompt design, and direct Adobe submission.

## Decisions / requirements
An asset is the durable business identity for one submitted image concept and remains stable across retries, re-audits, and derived files. A source file is the immutable bytes first accepted by storage; it has a content hash, original filename, media facts, and storage provenance. Derivatives, such as normalized JPEGs and thumbnails, reference the source or an explicitly named predecessor and are never treated as the original.

A batch groups an ingestion request and provides operational context, not ownership of an asset. The same content may appear in multiple batches, but deduplication policy must prevent accidental second processing. A QC audit is an immutable observation produced by a named policy version. It contains check results, evidence references, timestamps, and execution context. Findings are structured, severity-bearing explanations rather than free-form status text.

A metadata set represents generated, edited, validated, or approved title, keywords, and disclosure values. Every revision references its predecessor and creator or process. A review decision records actor, decision, reason, evidence versions, and policy version. A job represents a durable processing attempt and has its own lifecycle, retry count, cancellation state, and error details. An export identifies the exact asset, metadata revision, source hash, and packaged file hash.

Invariants include: originals are immutable; every derivative has a traceable parent; every decision references evidence that existed at decision time; READY requires a successful export and attributable human approval; stale evidence cannot authorize a newer source or metadata revision; and a failed job cannot silently advance an asset. Domain identifiers are opaque and stable, while display names are mutable and non-unique.

## Affected blueprint areas
This refines the SQLite image record, storage directories, QC engine, Gemini services, ExifTool packaging, API endpoints, and review dashboard. It is the conceptual foundation for documents 15–20 and 21–32.

## Dependencies
The model depends on the workflow in document 02, policy classifications in document 06, lifecycle storage in document 11, and error categories in document 12. It also requires an actor representation and a policy-version convention.

## Acceptance criteria
- Every entity has an owner, identity, lifecycle, and provenance rule.
- Original, derived, evidence, decision, job, and export relationships are reconstructable.
- READY eligibility can be evaluated without inspecting untracked files.
- Reprocessing preserves prior audits and decisions.
- Domain terms are consistent across later schemas and APIs.

## Risks / open questions
The product owner must decide whether an asset represents one file or a conceptual image across corrected derivatives. A local actor model may initially have one operator but should not prevent future identities. The retention period for rejected evidence and the exact export-manifest granularity remain unresolved.