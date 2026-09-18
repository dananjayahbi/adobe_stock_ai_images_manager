# 64 — Observability and Support Diagnostics

## Purpose
Define the evidence needed to understand processing behavior, user-visible failures, performance regressions, and provider or native-tool problems without collecting unnecessary personal or image data.

## Scope
This plan covers structured logs, metrics, traces or correlation context, health endpoints, support bundles, retention, redaction, and diagnostic UX. It does not replace the operations recovery steps or introduce a mandatory cloud telemetry service.

## Decisions / requirements
Every upload, job, audit, decision, retry, packaging attempt, and recovery action carries a correlation identifier and stable entity or batch identifier. Structured events include timestamp, application version, stage, outcome, duration, retry count, dependency category, and safe error code. They omit credentials, raw prompts unless explicitly approved, absolute paths where not needed, image bytes, and unbounded provider responses. User notes and generated metadata are treated as potentially sensitive.

Core metrics include intake counts by outcome, queue depth, stage duration, retry and terminal-failure counts, provider latency and rate limits, OCR and ExifTool availability, database lock events, disk usage, package verification failures, startup failures, and frontend error counts. Metrics support local diagnosis and bounded retention; collection must not make the UI or processing path dependent on a remote service.

Health is divided into liveness, core readiness, and optional dependency readiness. A Gemini outage does not imply loss of local data. Diagnostics show current version, migration state, tool versions, storage capacity, queue summary, and recent safe failures. Sensitive configuration values are represented only as present, absent, or invalid. Health checks have timeouts and cannot trigger expensive work.

A support bundle is user-initiated or explicitly authorized, previewable before export, bounded in size, and scrubbed. It includes configuration categories, versions, event summaries, and selected logs, not source images or secrets by default. Retention and deletion are documented. Diagnostic changes are tested for failure paths, clock skew, log rotation, and high-volume processing.

## Affected blueprint areas
This formalizes operational diagnostics, error taxonomy, provider provenance, job APIs, local deployment, frontend error presentation, and documents 12, 13, 37, 49, 61, and 63.

## Dependencies
It depends on correlation identifiers, structured error codes, local storage policy, privacy and legal review, and the support workflow. Performance budgets must account for instrumentation overhead.

## Acceptance criteria
- A failed item can be traced across API, job, dependency, and UI evidence.
- Health distinguishes core operation from optional provider readiness.
- Logs and support bundles contain no secrets or uncontrolled image content.
- Metrics remain bounded and useful during representative load.
- Operators can inspect version, tools, storage, migrations, and recent failures.
- Retention and deletion behavior is tested and documented.

## Risks / open questions
Over-logging can expose user material, while under-logging makes local failures unactionable. The team must decide whether any opt-in remote telemetry exists, define retention periods, choose a structured log format, and assign ownership for reviewing diagnostic signals.