# 55 — Unit Testing Strategy

## Purpose
Define fast, deterministic unit coverage for domain rules and isolated services so regressions are caught before integration or provider-dependent tests. Unit tests should prove policy behavior rather than duplicate implementation details.

## Scope
The strategy covers state transitions, threshold evaluation, validation, normalization decisions, metadata rules, idempotency calculations, error mapping, configuration parsing, and frontend pure utilities. It excludes database wiring, real external tools, network providers, and browser workflows.

## Decisions / requirements
Every pure domain rule receives table-driven tests for valid, invalid, boundary, and unknown inputs. Threshold tests include exactly-at-minimum values, just-below values, maximum file size, supported color spaces, sharpness calibration cases, OCR classifications, confidence boundaries, and policy-version changes. State-machine tests cover every allowed transition, forbidden transition, duplicate command, stale revision, retryable failure, and terminal failure. Tests assert both the resulting state and the reason or event recorded.

Image services should receive small deterministic fixtures or synthetic arrays and explicit dependency seams. Unit tests must not depend on a developer’s installed Tesseract, ExifTool, or Gemini credential. Provider adapters are tested with controlled response envelopes, malformed JSON, missing fields, timeouts, rate limits, and unexpected model output. Metadata tests enforce title length, keyword count, ordering, forbidden terms, normalization, deduplication, and human-edit preservation.

Backend tests use isolated temporary configuration and avoid shared mutable global state. Time, random identifiers, hashes, and retry scheduling are injected or controlled. Filesystem unit tests use temporary directories and assert that source files remain untouched. Frontend utility tests cover filter predicates, pagination cursors, status presentation, error extraction, optimistic update rollback, and safe display of untrusted filenames.

Tests should be named by behavior, remain fast enough for every change, and report coverage by risk area rather than relying solely on a global percentage. Mutation or boundary-focused sampling may be used for threshold and state logic. A failure must identify the policy or invariant it protects.

## Affected blueprint areas
This governs QC services, domain and state modules, schemas, metadata sanitization, packaging helpers, API client utilities, and documents 14–19, 27–44, and 50–54.

## Dependencies
The strategy depends on canonical enums, deterministic fixtures, provider contracts, configuration schema, and the chosen Python and TypeScript test frameworks. It must align with integration and AI test boundaries.

## Acceptance criteria
- All high-risk state, threshold, metadata, and validation rules have boundary tests.
- Unit runs require no network, provider secret, native global tool, or developer-specific path.
- Error and retry classifications are tested, including malformed dependencies.
- Tests are deterministic across supported Windows environments.
- Coverage reports identify untested policy branches and are reviewed before release.
- Test names and fixtures explain the invariant being protected.

## Risks / open questions
Synthetic image fixtures may not represent real defects, and excessive mocking can hide integration errors. The team must set minimum risk-area coverage, choose whether mutation testing is worthwhile, and establish ownership for updating fixtures when Adobe policy changes.