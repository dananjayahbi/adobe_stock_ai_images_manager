# Local operations runbook

## Startup

1. Confirm the application version and policy baseline.
2. Confirm the managed storage root is writable and has sufficient free space.
3. Check database migration state and core liveness/readiness.
4. Check OCR and ExifTool availability; missing optional tools must remain visible as degraded, not pass.
5. Check provider status. Gemini being unavailable does not block deterministic QC or manual review.
6. Open the local UI only after the checks are complete.

## Normal processing

1. Upload through the UI; never provide a server filesystem path.
2. Confirm accepted, duplicate, invalid, and deferred counts.
3. Observe durable job stage and counters.
4. Review hard blockers before warnings.
5. Inspect the normalized artifact and evidence.
6. Approve or reject with an attributable reason.
7. Confirm metadata and disclosure checklist before packaging.
8. Verify the manifest and package identity. READY does not imply marketplace submission.

## Recovery

- **Provider unavailable:** continue technical review; defer semantic and metadata work.
- **Queue stalled:** capture the correlation identifier, job stage, and safe diagnostics; restart only after checking whether a worker lease expired.
- **Package verification failure:** retry the packaging stage. Do not delete originals or edit database rows manually.
- **Disk low:** pause intake, preserve the managed root, and remove only documented regenerable temporary artifacts.
- **Database migration failure:** stop the application, preserve the pre-upgrade backup, and restore to an isolated location before attempting recovery.
- **Missing OCR or ExifTool:** install or repair the approved dependency, then rerun the affected stage; never claim the stage passed while unavailable.

## Support bundle

Export only the bounded, redacted support bundle. Review it before sharing. It must contain safe versions, health categories, correlation identifiers, and summarized failures—not images, prompts, credentials, absolute paths, or raw provider responses.

## Backup and restore

Back up the database, originals, required derivatives, metadata versions, audit history, provenance, manifests, and non-secret configuration. Validate hashes and representative package verification in an isolated restore location before replacing an active data root.
