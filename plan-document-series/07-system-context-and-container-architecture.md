# 07 — System Context and Container Architecture

## Purpose
Establish the boundaries and responsibilities of the local studio’s frontend, backend, persistence, storage, processing tools, and external AI provider. The architecture should preserve the blueprint’s modular separation while making operational ownership explicit.

## Scope
The architecture includes the browser-hosted Next.js interface, FastAPI service, SQLite database, local storage directories, deterministic QC services, OCR, Gemini adapter, ExifTool wrapper, background processing, and health diagnostics. It excludes cloud hosting, direct Adobe APIs, and multi-tenant infrastructure.

## Decisions and requirements
The browser is an operator client and must not hold provider credentials or perform trusted filesystem decisions. FastAPI owns validation, state transitions, file paths, job coordination, and access to SQLite and storage. The database records logical identity and evidence; files remain in managed directories with references rather than being embedded in database rows.

The ingestion boundary accepts multipart files, validates them, preserves originals, and creates records before dispatching work. QC services are deterministic and independently testable. The Gemini service is accessed through a provider adapter with timeout, response validation, and provenance. ExifTool is invoked through a narrow service that verifies results. The frontend consumes stable API schemas and does not infer state from path names.

Background work must be durable enough to recover after process restart; the blueprint’s illustrative framework background task is not sufficient as the final reliability design. All cross-container operations need correlation identifiers. External tools and provider availability must be represented in health checks without making a temporary provider outage look like data loss.

## Affected blueprint areas
This plan formalizes the architecture diagram, directory tree, FastAPI endpoints, core configuration and database modules, QC/Gemini/Exif services, storage directories, and Next.js components and API client. It guides documents 08–13, 21–26, 33, 45–49, and 58–66.

## Dependencies
The architecture depends on deployment choices, supported runtime versions, configuration and secret management, database and migration policy, file-safety rules, and durable job behavior. It also needs a defined local-network exposure model.

## Acceptance criteria
- Each component has a documented owner, trust boundary, and failure contract.
- Credentials never cross into the browser or logs.
- Original, derivative, database, and job responsibilities are separated.
- Provider, OCR, and ExifTool failures are observable and recoverable where possible.
- API clients can operate without knowing filesystem layout.
- The architecture supports restart reconciliation and idempotent finalization.

## Risks and open questions
SQLite concurrency and background workers may conflict if multiple processes are introduced. Local browser-to-backend access can expose files or credentials on a network interface. The owner must choose a durable job mechanism, decide whether frontend and backend run as one packaged application or separate processes, and define whether the system supports only one local operator.