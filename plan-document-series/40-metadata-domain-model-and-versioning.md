# 40 — Metadata Domain Model and Versioning

## Purpose
Define metadata as a first-class, auditable domain object rather than a pair of mutable fields on an image record. The model must distinguish generated suggestions, human edits, approved values, and embedded export values.

## Scope
This document covers metadata fields, versions, provenance, editing, validation state, approval linkage, and invalidation. It excludes the physical IPTC/XMP mapping and ExifTool execution defined in documents 41 and 42.

## Decisions / requirements
A metadata version belongs to one image artifact and contains title, ordered keywords, language, disclosure checklist state, optional user notes, validation results, source type, and lifecycle status. Source types include provider-generated, user-edited, imported, and approved. Versions are immutable after creation; editing creates a successor linked to its parent. The approved version is a pointer, not an in-place mutation.

Generated metadata must retain provider and prompt provenance. User edits retain the actor, timestamp, reason when required, and prior version. Validation records policy version, title and keyword limits, prohibited-term results, normalization changes, and unresolved warnings. Disclosure confirmation is modeled separately from searchable title and keywords because a portal checkbox cannot be assumed to be satisfied by embedded fields.

An approved version is eligible for packaging only when it validates against the current policy, references the exact artifact hash, and has no unresolved blocking issue. If the image is reprocessed, policy changes, the reviewer changes the decision, or a provider result is superseded, the approved pointer becomes stale. Stale metadata remains readable for history but cannot produce a new READY artifact without reconfirmation.

The API returns current approved metadata and version history through separate representations. It never exposes provider secrets or raw prompts by default. Export manifests include the approved version identifier and content hash. Metadata displayed to a reviewer must clearly indicate generated versus human-edited values.

## Affected blueprint areas
This replaces the blueprint’s mutable `title` and `keywords` assumption with a versioned model feeding Gemini generation, review, ExifTool embedding, ready packaging, and approval finalization.

## Dependencies
It depends on documents 03, 05, 14–20, 35–39, 41–44, and API schema rules. Canonical title, keyword, language, and disclosure requirements must be finalized upstream.

## Acceptance criteria
- Generated, edited, approved, and embedded metadata are distinguishable.
- Versions are immutable and linked to artifact and policy provenance.
- Approval requires current validation and exact source identity.
- Policy or source changes mark stale metadata clearly.
- Export manifests reference the approved metadata version.
- History supports reconstruction without mutating prior values.

## Risks / open questions
Imported metadata may contain unsupported claims or personal data. Version growth could increase storage and UI complexity. The team must decide whether users can manually enter metadata before AI generation, whether keyword order edits require a reason, and how long superseded versions remain available.