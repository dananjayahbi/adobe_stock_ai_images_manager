# 26 — Filesystem Atomicity and Cleanup

## Purpose
Ensure file transitions remain safe across crashes, antivirus locks, process termination, and database failures. The goal is no false READY state, no overwritten original, and recoverable temporary residue.

## Scope
The plan covers temporary names, atomic publication, database/file ordering, moves between storage roles, crash recovery, orphan classification, and cleanup. It applies to uploads, derivatives, thumbnails, quarantine, and exports.

## Decisions / requirements
Every write begins in a controlled temporary directory beneath the relevant storage root, using a generated name unrelated to user input. The writer flushes and closes the file, validates size and hash, and publishes through an atomic same-volume replacement or move. Cross-volume moves are not assumed atomic and must use copy, verification, and guarded retirement. Originals are never replaced by a derivative or packaged output.

Database references must identify the intended file role, hash, and publication state. A file is not authoritative merely because it exists in a directory. The preferred sequence records intent, publishes a verified file, commits the reference, and reconciles interrupted intent records on restart. If a database commit fails after publication, the file becomes a classified orphan rather than being immediately deleted. If publication fails after intent, the record remains recoverable or failed according to the stage.

Moves into quarantine or ready staging use the same verification rules. A ready export is published only after metadata embedding and read-back checks pass, and its manifest records source, normalized input, metadata revision, and output hash. Replacing an existing export requires matching identity and verified bytes; otherwise a new version is created. Windows file locks, antivirus scans, and open browser handles produce retryable errors with bounded attempts.

Cleanup scans only registered roots, ignores active temporary files younger than the safety window, and compares path, role, hash, and database reference. Unknown files are reported before deletion. Temporary residue is retained long enough for crash diagnosis, then removed according to retention policy. Cleanup operations are logged with actor, scope, counts, and results.

## Affected blueprint areas
This governs inbox, thumbnails, ready-to-upload, quarantine, ExifTool output, worker recovery, database references, and operations diagnostics.

## Dependencies
It depends on the domain file model, migrations, content hashes, retention, Windows deployment, and durable jobs. It also informs integration and recovery tests.

## Acceptance criteria
- No incomplete file is presented as an authoritative artifact.
- Crashes between file and database steps are recoverable and diagnosable.
- Atomic operations are used where supported and verified alternatives elsewhere.
- Original files cannot be overwritten or silently moved out of retention.
- Orphan and temporary cleanup is conservative and auditable.
- Antivirus and lock failures do not corrupt state.

## Risks / open questions
The exact storage-volume layout may affect atomicity. Windows rename semantics and antivirus quarantine can vary by installation. The team must decide whether cleanup requires a user confirmation every time and how long temporary artifacts remain.