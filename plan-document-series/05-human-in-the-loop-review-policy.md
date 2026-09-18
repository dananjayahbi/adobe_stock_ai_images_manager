# 05 — Human-in-the-Loop Review Policy

## Purpose
Define where automation may assist and where a reviewer must remain accountable. The policy prevents technical checks or AI confidence scores from becoming an unattended publishing mechanism.

## Scope
This document covers reviewer responsibilities, evidence presentation, approval, rejection, override, re-audit, disclosure confirmation, and auditability. It applies to individual and future batch actions. It does not prescribe visual design details beyond the evidence needed for a safe decision.

## Decisions and requirements
Automation may inspect dimensions, color, sharpness, OCR signals, semantic artifacts, and metadata quality. It may prioritize work and recommend pass, flag, or retry. It may not independently approve an image for ready staging. A human must inspect the source at an appropriate zoom, consider technical and semantic evidence, confirm that metadata is truthful, and acknowledge generative-AI and legal-risk prompts before approval.

Hard technical failures cannot be overridden without an explicit reason and a policy-controlled exception path. Warnings may be overridden when the reviewer has sufficient evidence and the override is recorded. Semantic confidence is never a substitute for inspection. If an AI response is missing, malformed, stale, or contradictory, the item remains unresolved or is routed to manual review.

The review record should capture actor, timestamp, decision, reason, evidence version, policy version, and source hash. Re-audit is available after a corrected derivative or changed provider configuration, but a re-audit must not erase prior findings. A reviewer can reject an item without deleting the original; rejected content moves to a defined quarantine or retained-rejected state.

## Affected blueprint areas
This policy affects the dashboard’s inspection modal, status transitions, approval and rejection endpoints, semantic audit contract, metadata finalization, audit history, and future bulk-action UX. It is consumed by documents 02, 06, 39, 44, 50–55, and 65.

## Dependencies
The policy requires typed QC and AI evidence, a domain decision model, identity or local actor representation, state transition rules, and an error strategy for incomplete processing. It also requires current legal and Adobe policy baselines.

## Acceptance criteria
- No route can place an item in READY without an attributable human approval.
- Reviewers see source evidence, failed checks, warnings, AI findings, and metadata before acting.
- Overrides require reasons and preserve the original automated result.
- Re-audits append evidence and do not destroy prior decisions.
- Bulk operations isolate ineligible or failed items and summarize outcomes.
- The policy is testable through API, integration, and end-to-end scenarios.

## Risks and open questions
A local single-user application still needs an actor model, even if the initial actor is “local operator.” Review fatigue may cause superficial approvals, especially at high throughput. The owner must decide how much zoom and comparison functionality is mandatory, whether warning overrides need a second confirmation, and whether a batch-level attestation is acceptable in addition to per-item decisions.