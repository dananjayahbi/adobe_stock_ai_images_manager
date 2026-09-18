# 10 — Configuration and Environment Management

## Purpose
Define how paths, thresholds, provider settings, secrets, ports, concurrency, feature flags, and policy versions are supplied, validated, and exposed safely. Configuration must be explicit enough for reproducibility without leaking sensitive data.

## Scope
Configuration covers storage roots, database location, API and frontend URLs, upload limits, QC thresholds, model names, timeouts, retry budgets, worker concurrency, batch limits, OCR settings, metadata limits, logging levels, and optional provider operation. It includes development, test, and local-user environments.

## Decisions and requirements
Configuration has typed defaults suitable for a safe local installation, with environment or user settings able to override them only through validated fields. Secrets such as Gemini credentials are never committed, returned by health endpoints, embedded in frontend bundles, or written to ordinary logs. The application should distinguish missing provider credentials from provider outage and support a no-provider mode that still performs deterministic QC and manual review.

Policy values are versioned and recorded with audit results. Thresholds must not be changed by an arbitrary request parameter. Operational settings such as worker count and upload size need bounded ranges to prevent accidental resource exhaustion. Paths are resolved under approved roots; user-provided filenames cannot redefine storage locations.

A configuration diagnostic should report effective non-secret settings, source category, validation warnings, and tool discovery. Changes that affect active jobs should apply at a clear boundary, ideally new jobs, rather than changing the meaning of an in-flight audit.

## Affected blueprint areas
This plan refines `core/config.py`, storage constants, QC thresholds, Gemini model selection, ExifTool and OCR configuration, API limits, frontend API URL, and health diagnostics from the blueprint. It is consumed by documents 07–13, 21–37, 45–49, and 64–66.

## Dependencies
Configuration depends on the policy baseline, deployment model, version matrix, storage lifecycle, error taxonomy, security controls, and provenance schema. It also requires a selected Windows secret-storage approach.

## Acceptance criteria
- Every configurable value has a type, default, allowed range, and documentation.
- Effective configuration is testable without revealing secrets.
- Policy and model versions are persisted with relevant outputs.
- Invalid settings fail early with actionable diagnostics.
- Provider-disabled operation remains safe and understandable.
- Configuration changes cannot escape managed filesystem roots or bypass approval rules.

## Risks and open questions
Environment variables alone are inconvenient for a desktop user, while a settings UI can expose powerful unsafe options. Threshold changes can invalidate comparisons across batches. The owner must decide which values are user-editable, how settings are encrypted or stored, whether model selection is fixed per release, and how configuration migrations are handled.