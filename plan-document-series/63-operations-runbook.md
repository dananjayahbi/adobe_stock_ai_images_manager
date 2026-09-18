# 63 — Operations Runbook

## Purpose
Give an operator or support maintainer a concise, safe procedure for running the studio, recognizing failures, preserving evidence, and recovering without editing the database or managed files manually.

## Scope
The runbook covers startup and shutdown, health checks, routine processing, provider configuration, queue observation, logs, storage checks, backup, retry, restart recovery, degraded operation, and escalation. It does not replace implementation-specific error contracts or the Windows installer guide.

## Decisions / requirements
Startup begins with checking application version, database migration state, writable data roots, disk capacity, native tool readiness, and provider configuration status. The operator opens the local UI only after liveness and readiness diagnostics are meaningful. Normal operation is upload, observe processing, inspect blockers, make human decisions, review metadata, and verify ready packages. The runbook states which actions are safe to repeat and which require support review.

Failures are handled by symptom and evidence: application will not start, upload rejected, queue stalled, OCR or ExifTool unavailable, provider rate-limited, database locked, package verification failed, disk space low, or output missing. Each procedure collects a correlation identifier, affected batch or image, status, last successful stage, relevant sanitized logs, and current disk/tool health before attempting recovery. Recovery favors retrying the failed stage, restarting a worker or application, reconciling durable jobs, or restoring a backup; it never instructs users to edit rows or rename files manually.

Backups include database, configuration where safe, provenance, and required managed outputs, with secrets excluded or separately protected. A restore is performed to an isolated location first and validated using record counts, hashes, and sample package verification. Retention and deletion follow the data policy. Logs are bounded, rotated, and scrubbed; support bundles contain only approved diagnostics.

Degraded modes are explicit. If Gemini is unavailable, deterministic QC and local review may continue while semantic work is deferred. If packaging tools are unavailable, approval evidence remains intact but READY is not claimed. If storage is near capacity, new intake pauses with an actionable warning.

## Affected blueprint areas
This operationalizes diagnostics, error taxonomy, storage, backups, job recovery, provider controls, packaging, and Windows deployment described in documents 09–13, 20, 25–26, 37, 43–44, and 61.

## Dependencies
It depends on stable health and job APIs, correlation IDs, backup tooling, log redaction, durable checkpoints, and an approved support-access model.

## Acceptance criteria
- A trained operator can start, stop, inspect health, and process a batch safely.
- Common failures have symptom, evidence, recovery, and escalation steps.
- Degraded provider and native-tool modes are visible and non-destructive.
- Backups and restores are tested with integrity checks.
- Support artifacts exclude secrets and uncontrolled source data.
- No procedure requires direct database or managed-file editing.

## Risks / open questions
A local product may have no always-on operations owner. The team must assign support responsibility, choose backup destinations, set disk and log thresholds, define escalation response times, and decide whether remote support is permitted.