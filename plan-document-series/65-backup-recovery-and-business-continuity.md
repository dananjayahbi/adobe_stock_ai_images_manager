# 65 — Backup, Recovery, and Business Continuity

## Purpose
Protect the operator’s source images, decisions, metadata, provenance, and ready packages from disk failure, accidental deletion, failed upgrades, and unrecoverable processing interruptions.

## Scope
The plan covers backup contents, frequency, storage destinations, encryption and access, consistency, restore validation, disaster scenarios, retention, and continuity procedures for a local single-operator application. It excludes enterprise replication and direct Adobe account recovery.

## Decisions / requirements
A recoverable set includes the database, original and required derived files, approved metadata versions, review history, AI provenance, package manifests, application and policy version references, and configuration that does not contain secrets. Secrets are either re-entered after restore or stored through an approved protected mechanism. Temporary work and regenerable thumbnails need not be backed up if rebuild behavior is proven.

Backups must be consistent with active jobs. The system either quiesces writes briefly, uses a safe database backup mechanism, or records a checkpoint and includes all referenced files. File references are validated against content hashes and manifests. Backup names include version and creation time but reveal no sensitive metadata. Destinations should support a second physical or user-controlled location, with guidance on removable drives or protected folders and the risks of same-disk backups.

Restore is a deliberate workflow that first validates the backup in an isolated location. It checks database migrations, record counts, file existence, hashes, sample thumbnail generation, metadata verification, event history, and package readiness. Restoration must not silently merge conflicting records into an active store. The user receives a preview and chooses a new data root or replacement under documented safeguards.

Business continuity covers disk-full, corrupted database, lost application installation, unavailable Gemini, and failed native tools. Deterministic review and preserved originals should remain useful even when provider-dependent stages are paused. Recovery objectives are set for data loss and time to resume, then tested on the supported Windows baseline.

## Affected blueprint areas
This governs retention, storage layout, database migrations, idempotency, packaging, provenance, operations, diagnostics, and Windows upgrade behavior.

## Dependencies
It depends on storage paths, hashes, migration support, privacy and retention policy, secret handling, and the selected backup implementation. It also depends on support ownership and user education.

## Acceptance criteria
- Backup scope and exclusions are explicit and reviewable.
- Active work cannot produce a backup that claims complete state falsely.
- Restore validation detects missing or mismatched files.
- A failed upgrade can be recovered without overwriting the only copy.
- Provider or tool outages do not destroy deterministic evidence or originals.
- Recovery objectives and restore test results are documented.

## Risks / open questions
Users may not perform backups, and same-disk copies do not protect against hardware failure. The team must decide whether backup is automatic or user-triggered, whether encryption is required, acceptable recovery point and time objectives, and how much data can be restored to a new machine.