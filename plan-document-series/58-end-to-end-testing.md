# 58 — End-to-End Testing

## Purpose
Prove that a real operator can complete the supported local workflow through the browser, including partial failures and recovery, without relying on internal implementation shortcuts.

## Scope
E2E coverage includes application startup, upload, batch progress, queue filtering, inspection, approval, rejection, metadata review, packaging, restart recovery, and diagnostics. It includes supported error paths but excludes large-scale performance, deep provider benchmarking, and direct marketplace submission.

## Decisions / requirements
E2E tests run against a built or release-like frontend and backend with isolated temporary storage and a disposable database. External AI calls use a deterministic provider substitute by default; a separately controlled smoke lane may use the real provider only with explicit credentials and cost approval. Fixtures cover valid JPEGs, low resolution, blurry images, malformed files, duplicates, semantic flags, metadata violations, and packaging failures.

The primary journey verifies upload response classification, visible processing progress, evidence display, human approval, metadata confirmation, metadata embedding verification, and ready-package presentation. Additional journeys verify that one bad file does not hide successful siblings, retry actions preserve identity, stale revisions produce a clear conflict, a provider outage leaves deterministic results available, and a restart reconciles durable jobs. Browser tests must assert user-visible outcomes and safe actions rather than private DOM implementation details.

E2E assertions include accessibility landmarks and keyboard completion for the core path. Tests capture screenshots or traces only when useful for diagnosing failures and must avoid storing source images or secrets in artifacts. Test data is reset between scenarios. Timing assertions use bounded eventual conditions tied to observable state, not arbitrary sleeps.

The suite is split into smoke tests for every change and broader regression tests for release candidates. Flaky tests are quarantined with an owner and expiry date; retries may aid diagnosis but cannot turn an unstable test into a pass without reporting the original failure.

## Affected blueprint areas
This validates frontend architecture, API routes, job progress, storage lifecycle, QC and AI boundaries, approval and finalization states, and documents 02, 21–26, 45–54, and 56–57.

## Dependencies
It depends on a supported browser matrix, deterministic provider substitute, stable fixtures, test configuration, and a reliable way to start and stop local services on Windows.

## Acceptance criteria
- Smoke E2E covers the complete happy path from upload to ready package.
- Partial, retry, conflict, outage, and restart paths are covered.
- Tests use observable user outcomes and isolated data.
- Core workflow passes keyboard and accessibility smoke checks.
- Artifacts are safe, bounded, and useful for diagnosis.
- Flaky failures are visible and tracked rather than silently retried away.

## Risks / open questions
Browser timing and native tools can make local E2E fragile. The team must choose the browser automation framework, define release versus per-commit suites, decide whether ExifTool and OCR run in E2E or integration lanes, and document startup diagnostics.