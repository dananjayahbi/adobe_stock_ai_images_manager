# 02 — User Workflows and State Transitions

## Purpose
Describe the operator journey from batch upload to ready-to-upload staging and establish a shared vocabulary for lifecycle states. The workflow must make automated work observable while keeping decisions reversible where practical and human approval explicit.

## Scope
The workflow covers selecting or dropping files, intake validation, thumbnail creation, technical audit, semantic audit, review, approval, rejection, retry, metadata generation, embedding, verification, and final staging. It includes normal, partial-failure, duplicate, provider-outage, and cancellation journeys. Direct marketplace submission and account-management workflows are outside scope.

## Decisions and requirements
A newly received file is first recorded as pending and associated with a batch. Intake must report per-file results so one invalid or duplicate file does not conceal successful uploads. Processing transitions through auditing only after the source is safely stored. Deterministic QC runs before paid semantic analysis and may produce a hard flag that prevents unnecessary API usage.

The review surface must distinguish technical failure, semantic concern, incomplete processing, and reviewer decision. A passed automated audit is eligible for review, not automatically ready. The reviewer may approve, reject, request re-audit, or leave an item unresolved. Approval starts metadata generation and packaging; failures in those steps must preserve the approved decision while exposing a recoverable finalization error rather than falsely showing READY.

Retry must be scoped to the failed stage and must not duplicate database records, charge the provider unnecessarily, or overwrite the original. A completed READY action must be idempotent. Reopening or changing a decision must create an auditable event and invalidate any stale packaged output if the source or approved metadata changes.

## Affected blueprint areas
This plan refines the blueprint’s status comment—PENDING, AUDITING, PASSED, FLAGGED, APPROVED, READY—the upload endpoint, background audit task, approval endpoint, dashboard polling, and ready directory. It informs documents 14–20, 25–26, 39, 44, 49, and 50–56.

## Dependencies
The workflow depends on the domain entities and state machine, upload and file-safety contracts, QC and AI response contracts, metadata packaging rules, and API schemas. It also depends on an explicit error taxonomy so retryable and terminal outcomes are not represented as ambiguous flags.

## Acceptance criteria
- Every user-visible stage has a defined entry condition, exit condition, and failure outcome.
- Partial batches show successful, rejected, duplicate, and failed items separately.
- Approval cannot bypass required evidence or mandatory policy disclosure fields.
- Retries are stage-aware and idempotent.
- A failed package never appears in the ready pool as if it were complete.
- State and action history are sufficient to reconstruct who decided what and when.

## Risks and open questions
The blueprint’s single status field may be insufficient for concurrent audit, review, and packaging jobs; separate job and decision records may be required. BackgroundTasks may not survive process restarts, so durable jobs are an architectural dependency. The product owner must decide whether rejection is terminal or reversible, whether an approved item can be edited in place, and whether batch approval is included in MVP. Polling every three seconds is a useful prototype behavior but may be inefficient for large batches.