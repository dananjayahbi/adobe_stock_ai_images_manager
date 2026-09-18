# 38 — AI Audit Provenance and Model Versioning

## Purpose
Make every AI-assisted decision reproducible enough for review, diagnosis, policy changes, and provider migrations without retaining unnecessary sensitive data.

## Scope
The provenance contract covers artifact identity, prompts, schemas, model and SDK versions, configuration, timestamps, request outcomes, hashes, and relationships between attempts. It applies to semantic audits and metadata generation.

## Decisions / requirements
Every attempt references the immutable source or normalized artifact hash, operation type, provider name, model identifier, provider SDK version, response schema version, prompt version, policy version, and application release. It records creation time in UTC, duration, attempt number, request correlation identifier when available, and outcome category. Configuration affecting generation, including temperature, response mode, and safety settings, is represented by a redacted canonical hash or approved fields; secrets and raw credentials are excluded.

Prompt text is version-controlled as an application artifact and referenced by stable identifier and content hash. The persisted record may retain the exact prompt only when privacy and retention policy permit; otherwise the hash plus release artifact is authoritative. Raw provider responses are retained only under a bounded diagnostic policy and must be redacted before ordinary display. Validated findings and metadata are stored separately from transport envelopes.

A model or prompt change never mutates historical evidence. It creates a new attempt and, if selected by policy, invalidates prior eligibility or metadata approval. Comparisons between attempts show changed findings, confidence, keywords, and validation outcomes. A cached result is linked to its original attempt rather than copied as unexplained current truth.

Provenance is visible to reviewers at an appropriate level: provider, model, run time, artifact, policy version, and validation status. It is exportable for diagnostics without including API keys, full personal data, or unbounded image bytes. Deletion and retention jobs must preserve required audit references or mark them unavailable explicitly.

## Affected blueprint areas
This extends the blueprint’s semantic confidence, heuristic breakdown, generated metadata fields, logs, and audit history into explicit AI evidence. It supports documents 34–40, 42, 44, 65, and 66.

## Dependencies
It depends on content hashing, retention and backup policy, configuration versioning, provider integration, schema validation, and audit-event persistence. Legal and privacy review must approve prompt and response retention.

## Acceptance criteria
- Every AI result is linked to an exact artifact and versioned execution context.
- Historical attempts remain immutable and comparable.
- Secrets and unnecessary sensitive content are excluded from provenance.
- Model, prompt, schema, policy, and SDK versions are queryable.
- Reuse and retries point to original evidence rather than duplicating unexplained data.
- Diagnostic export is bounded and privacy-reviewed.

## Risks / open questions
Provider request identifiers and model versions may be unavailable or unstable. Retaining prompts or responses can expose user content. The project must decide retention duration, whether raw responses are ever stored, and which model changes force mandatory re-audit.