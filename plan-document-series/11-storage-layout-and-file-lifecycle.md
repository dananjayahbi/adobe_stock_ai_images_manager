# 11 — Storage Layout and File Lifecycle

## Purpose
Define the managed filesystem layout and the lifecycle of originals, derivatives, temporary files, rejected assets, and ready-to-upload exports. The design must preserve evidence and prevent accidental data loss.

## Scope
The lifecycle covers intake, original preservation, thumbnails, normalized derivatives, quarantine, processing temporaries, ready files, manifests, archives, and cleanup. It includes database references and restart reconciliation. It excludes remote backup implementation, which is covered later.

## Decisions and requirements
The blueprint’s inbox, thumbnails, and ready-to-upload directories are the minimum visible structure. The implementation should add managed locations for temporary work, quarantine or rejected content, manifests, and diagnostics rather than mixing transient and user-facing files. Originals are immutable after successful intake. Derived files carry a stable asset identity and processing version; filenames alone are not identity.

Writes occur through temporary files followed by validated atomic replacement or move. A ready file is created only after metadata embedding and read-back verification. The system must avoid overwriting an existing output with a different asset or metadata version. Duplicate filenames are collision-safe, and content hashes support deduplication and reconciliation.

Cleanup is conservative: active job inputs and evidence cannot be deleted automatically. Orphaned thumbnails and temporary files may be removed only after age, job, and database checks. Quarantine retains the source and failure evidence for the configured retention period. Export manifests identify source, final path, metadata version, policy version, and packaging time.

## Affected blueprint areas
This document expands the blueprint storage tree, upload endpoint paths, thumbnail generation, ready-pool stage, ExifTool copy behavior, database path references, and future backup and diagnostics functions. It informs documents 19–26, 40–44, 59, 63, 65, and 66.

## Dependencies
The lifecycle depends on domain identity, deduplication, file validation, normalization, atomicity, database migrations, retention policy, and packaging contracts. Windows path behavior and antivirus interference must be tested.

## Acceptance criteria
- Originals survive every audit, rejection, retry, and packaging failure.
- Every managed file has an owning asset or an auditable temporary/manifest purpose.
- Ready outputs are collision-safe, verified, and traceable to a source hash.
- Restart reconciliation detects missing, orphaned, and inconsistent files.
- Cleanup cannot remove active or historically required evidence.
- Storage paths are configurable but remain under approved roots.

## Risks and open questions
Large batches may consume substantial disk space through originals, thumbnails, and derivatives. Antivirus or indexing software can hold files open on Windows. The owner must choose retention periods, whether rejected assets are archived or quarantined indefinitely, whether normalized JPEGs become the packaging source, and how users export or restore the complete asset-plus-database set.