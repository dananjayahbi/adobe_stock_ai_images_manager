# 57 — AI Evaluation and Safety Testing

## Purpose
Establish a repeatable evaluation process for semantic auditing and metadata generation so provider changes improve or preserve useful behavior without turning probabilistic output into an unjustified publishing decision.

## Scope
The plan covers prompt and model evaluation, response parsing, safety and policy cases, quality benchmarks, cost and latency observations, regression datasets, human adjudication, and provider failure behavior. It excludes general deterministic QC and direct Adobe submission.

## Decisions / requirements
AI output is evidence and proposal, never autonomous approval. Evaluation datasets must include representative clean images, anatomy defects, geometry artifacts, misleading text, trademarks, celebrity-like subjects, ambiguous commercial scenes, low-quality images, and cases where the correct result is uncertainty. Each fixture has an expected risk category, not only a binary pass label. Sensitive or copyrighted material is excluded or governed by an approved local data policy.

The evaluator records model identifier, prompt version, request settings, timestamp, parsing result, latency, token or cost estimate when available, and human adjudication. A change is assessed for false negatives, false positives, abstention quality, metadata relevance, prohibited terms, title constraints, keyword ordering, and consistency. Hard safety or policy regressions block release even if average confidence improves. The evaluation must distinguish provider failure, schema failure, and substantive model disagreement.

Malformed, truncated, adversarial, or instruction-injected image/context responses are tested. Sanitization rejects invalid JSON shapes, unsupported fields, unsafe lengths, invented evidence, and metadata that violates forbidden-term rules. Retries are bounded and must not multiply cost without an observable reason. Provider outage tests confirm the user can continue deterministic review or defer the affected stage.

A small blinded human review panel or owner adjudication is required for benchmark updates. Disagreements become explicit policy questions rather than silent label changes. Production-like samples may be added only with provenance, retention, and redaction controls. Evaluation reports are versioned with the application and model configuration.

## Affected blueprint areas
This governs Gemini integration, semantic audit and metadata contracts, sanitization, retry and cost controls, provenance, human override, review UX, and release testing.

## Dependencies
It depends on stable prompt versions, representative fixtures, policy baselines, provider quotas, and an approved method for storing evaluation evidence. It must align with deterministic QC so AI is not evaluated on cases already rejected locally unless that behavior is intentional.

## Acceptance criteria
- A versioned benchmark covers clean, defective, ambiguous, and policy-sensitive cases.
- Parser and sanitizer tests reject malformed or unsafe responses.
- Model changes report false-negative and false-positive impact plus latency/cost observations.
- Provider outage and rate-limit behavior is recoverable and visible.
- Human adjudication supports benchmark changes and records disagreements.
- No AI result alone can bypass required human approval.

## Risks / open questions
Model behavior may drift without a visible version change. Labels can encode reviewer bias, and small datasets can create false confidence. The team must choose benchmark size, acceptance thresholds, retention rules, and whether live-provider smoke tests are permitted in CI.