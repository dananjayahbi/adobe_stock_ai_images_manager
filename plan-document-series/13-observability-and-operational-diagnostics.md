# 13 — Observability and Operational Diagnostics

## Purpose
Make local processing understandable and supportable through structured logs, metrics, audit events, health checks, and safe diagnostic bundles. Operators must be able to explain a stuck or failed asset without opening the database manually.

## Scope
Observability covers request and job correlation, lifecycle events, QC measurements, provider calls, retries, state changes, packaging verification, performance metrics, health checks, and exportable diagnostics. It excludes a hosted monitoring platform; the initial design is local-first.

## Decisions and requirements
Logs should be structured and include timestamp, severity, component, asset or batch identifier, job identifier, stage, duration, and outcome. They must exclude provider credentials, full image contents, unnecessary OCR text, and sensitive paths where possible. Audit events are separate from operational logs: they record decisions, overrides, policy versions, model versions, metadata versions, and actor identity in a durable, queryable form.

Metrics should cover intake counts, state counts, processing latency by stage, queue depth, retry counts, provider failures and latency, OCR and ExifTool availability, disk usage, and ready-package verification failures. Metrics must be useful without implying that a pass rate equals marketplace acceptance. Health checks distinguish liveness, database readiness, filesystem readiness, native-tool readiness, and provider configuration or reachability.

A diagnostic bundle can include sanitized configuration, version matrix, health results, selected logs, job summaries, and asset identifiers. It must require explicit user action, redact secrets, and avoid copying source images unless the user chooses a controlled support export. Correlation IDs make one asset traceable across API, worker, provider, and packaging records.

## Affected blueprint areas
This document extends the FastAPI service, background audit task, QC/Gemini/ExifTool services, SQLite records, dashboard status and health views, storage diagnostics, and operations runbook. It informs documents 07, 10–12, 25–26, 33–44, 45–49, 58–66.

## Dependencies
Observability depends on the domain event model, job identifiers, error taxonomy, configuration redaction rules, provider provenance, retention policy, and a selected logging implementation. It also depends on Windows file and process diagnostics.

## Acceptance criteria
- A supportable asset journey can be reconstructed from structured events.
- Health checks identify missing tools, unusable storage, database issues, and provider configuration separately.
- Logs and bundles redact secrets and minimize personal or image-derived data.
- Key latency, queue, failure, and disk metrics are available locally.
- Packaging and approval events include policy and model provenance.
- Diagnostic export is deliberate, bounded, and documented.

## Risks and open questions
Verbose logs can consume disk space or expose OCR text and filenames. Local metrics may be insufficient for long-term trend analysis. Provider requests may contain sensitive images and need careful event representation. The owner must decide retention and rotation limits, whether users can attach source files to support bundles, and whether a future hosted telemetry option is acceptable under privacy requirements.