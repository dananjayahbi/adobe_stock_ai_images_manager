# 20 — Data Retention, Backup, and Recovery

## Purpose
Protect original images, decisions, evidence, and ready exports while defining recoverable cleanup behavior for a local desktop application.

## Scope
This document covers retention classes, backup contents, restore order, orphan cleanup, integrity checks, rejected and quarantined assets, and recovery reporting. It excludes cloud backup implementation and legal retention advice.

## Decisions / requirements
Original source files and their hashes are retained until an explicit user action or configured policy permits deletion. Normalized files, thumbnails, OCR evidence, provider responses, logs, and diagnostic bundles have separate retention classes because they differ in size, sensitivity, and regeneration cost. Human decisions, state events, policy versions, export manifests, and source provenance are retained longer than transient worker logs.

Backups must include the SQLite database and the storage objects needed to restore authoritative assets, with a manifest listing relative paths, sizes, hashes, and schema version. A backup is not complete until the manifest and database are internally consistent. Sensitive provider payloads and credentials are excluded or protected according to privacy settings. Backups must not be placed in the active processing directories.

Restore proceeds by validating the backup, restoring the database to an isolated location, restoring files, checking hashes and references, and only then reopening normal processing. If a file is missing, the affected asset becomes recovery-required or review-blocked; it must not be marked READY. If extra files exist without database references, reconciliation classifies them as recoverable orphan, temporary residue, or unknown and never deletes them automatically on first detection.

Cleanup is staged: identify candidates, display counts and reasons, create a record of the cleanup plan, move files to a recoverable quarantine when feasible, and permanently delete only after a configured grace period. Ready exports should be retained until the user confirms external submission or deletion. A consistency check periodically compares database references, hashes, storage roles, and export manifests.

## Affected blueprint areas
This governs storage directories, SQLite persistence, ready-to-upload files, quarantine, logs, diagnostics, startup recovery, and operations documentation. It supports documents 11–13, 17–20, 26, 43, 59, and 66.

## Dependencies
Retention requires privacy and legal decisions, filesystem atomicity, migration compatibility, content hashes, and an installation-specific backup location. Windows permissions and antivirus behavior must be considered.

## Acceptance criteria
- Retention classes and deletion authority are explicit.
- Backup manifests prove database and file integrity.
- Restore tests recover sources, decisions, evidence references, and ready exports.
- Orphans are reported before any destructive cleanup.
- Missing or corrupt files block misleading READY status.
- Users can inspect and cancel a cleanup plan during its grace period.

## Risks / open questions
The project lacks a required retention period and backup destination policy. Large originals may exceed convenient local backup capacity. Encryption, password management, and removable-drive support need decisions. Whether provider data may be retained at all depends on terms and privacy review.