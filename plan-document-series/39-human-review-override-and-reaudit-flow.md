# 39 — Human Review Override and Re-Audit Flow

## Purpose
Define safe manual resolution of automated findings, including permitted overrides, reviewer reasons, corrected derivatives, re-audits, and preservation of accountability.

## Scope
This document covers review decisions after deterministic QC and AI analysis, override eligibility, reason capture, re-audit triggers, stale evidence, actor identity, and history. It does not define visual layout or general API route syntax.

## Decisions / requirements
A reviewer may approve, reject, defer, request re-audit, or edit proposed metadata only after the required evidence is available. Approval is never implied by a technical or semantic pass. Hard technical failures are not overrideable unless policy explicitly defines an exception and the reviewer supplies a structured reason; unexplained free-text overrides are insufficient. Warnings and uncertain semantic findings may be overridden when the reviewer confirms visual inspection and records the basis.

A reviewer decision references the exact artifact hash, audit versions, policy version, metadata version, and actor. The initial local actor identity is a configured operator identity, but the event model must support stronger authentication later. Each action records UTC time, prior state, new state, reason code, optional note, and whether the action was individual or batch-derived. History is append-only.

Re-audit is required when the source derivative changes, a policy threshold changes, a provider model or prompt changes under policy, an earlier response was invalid or incomplete, or a reviewer explicitly requests another examination. Re-audit creates new evidence and marks dependent approval or packaging stale. It must not erase a previous rejection, dismissal, or override. A corrected derivative remains linked to the original source and receives a new content hash.

The system must prevent stale reviewers from overwriting newer decisions. Actions include an expected version or revision token, and conflicts return the current state for reinspection. Rejection preserves the original and moves the item to a retained rejected or quarantine lifecycle. Ready output is invalidated when a decision or approved metadata changes.

## Affected blueprint areas
This operationalizes the human-in-the-loop policy, status transitions, approval endpoint, audit history, storage lifecycle, and review dashboard. It feeds documents 16, 19, 39, 40, 44, 47, and 54.

## Dependencies
It depends on typed QC and AI evidence, provenance, domain entities, state rules, actor/session handling, and file lifecycle policy. Legal and product owners must define non-overrideable categories.

## Acceptance criteria
- Every approval has an identifiable actor, reason, evidence version, and timestamp.
- Hard failures cannot be silently bypassed.
- Re-audits append evidence and invalidate stale dependent artifacts.
- Concurrent stale actions are rejected without data loss.
- Rejection preserves originals and remains traceable.
- Batch actions isolate ineligible items and report per-item outcomes.

## Risks / open questions
A single local operator identity may provide weak accountability. Reviewers may overuse warnings or batch actions. The owner must approve exception categories, require a second confirmation or second actor for high-risk overrides, and decide the retention period for rejected evidence.