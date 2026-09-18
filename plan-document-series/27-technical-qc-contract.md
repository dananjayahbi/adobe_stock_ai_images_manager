# 27 — Technical QC Contract

## Purpose
Define a stable, deterministic contract for local technical quality checks so thresholds, evidence, review decisions, and tests remain consistent across detectors.

## Scope
The contract covers inputs, outputs, rule identity, severity, evidence, policy versions, deterministic execution, and aggregation. Individual resolution, color, sharpness, and OCR methods are specified in documents 28–31.

## Decisions / requirements
A QC run accepts a registered image artifact, its content hash, detector configuration, policy version, and execution context. It returns an immutable audit with overall outcome, ordered check results, warnings, hard failures, informational signals, tool versions, elapsed time, and evidence references. A check result includes rule identifier, detector version, observed value or bounded fact, threshold or rule expression, severity, explanation, and reproducibility fields.

The contract distinguishes PASS, WARN, FAIL, REVIEW_REQUIRED, and NOT_EVALUATED. NOT_EVALUATED is never treated as pass. Aggregation is deterministic: a hard failure blocks technical eligibility; unresolved safety or processing errors require review; warnings remain visible; informational results do not alter eligibility. The aggregator must retain all individual findings even when one failure determines the overall result.

Inputs are read-only and selected by hash. Detectors must not mutate the source or share hidden global state. Same input bytes, policy, library versions, and configuration should produce the same result within documented numeric tolerance. Non-deterministic environmental factors, such as OCR model changes, are recorded as detector-version changes and trigger a new audit.

Evidence is bounded and privacy-aware. It may include dimensions, color profile identifiers, measured sharpness, OCR snippets subject to redaction, and artifact paths or regions. It must not embed full images or secrets in database rows. Evidence references point to retained artifacts with integrity hashes. A rerun appends a new audit and never edits history.

## Affected blueprint areas
This formalizes the blueprint’s deterministic QC stage, heuristic breakdown JSON, failure reasons, review badges, state eligibility, configuration, and fixture strategy.

## Dependencies
It depends on policy calibration, image validation, normalization, storage provenance, database entities, and retention. Downstream semantic and metadata contracts must not confuse technical pass with commercial acceptance.

## Acceptance criteria
- Every check has a stable rule and detector version.
- Results distinguish failure, warning, review, and not evaluated.
- Aggregation is deterministic and explainable.
- Evidence is bounded, hashed, and linked to the exact input.
- Historical audits remain readable after threshold changes.
- Tests can assert both individual findings and aggregate eligibility.

## Risks / open questions
Numeric reproducibility may vary by OpenCV, OCR, and image-library versions. The product must decide whether normalization output or original input is authoritative for each detector. Evidence redaction and retention rules for OCR text need privacy approval.