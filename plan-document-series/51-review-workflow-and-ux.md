# 51 — Review Workflow and UX

## Purpose
Translate the human-in-the-loop policy into an efficient, understandable review experience. The interface must accelerate inspection while preserving deliberate human approval, visible uncertainty, and reversible recovery from mistakes.

## Scope
The scope includes upload feedback, processing progress, review triage, 100% inspection, evidence interpretation, approval and rejection, overrides, metadata review, packaging confirmation, and failure recovery. It excludes automated submission to Adobe Stock and broad multi-user collaboration.

## Decisions / requirements
Upload begins with an explicit batch summary showing accepted, duplicate, invalid, and deferred files. Processing progress must distinguish queued, running, completed, blocked, and failed work; an animated indicator alone is insufficient. The user can leave the page and return to the same batch without losing context. Refresh and restart must not create a second action or hide an existing job.

Review is designed for triage first and inspection second. Cards show a concise reason for attention, not merely a color badge. A reviewer can sort by hard technical blocker, semantic confidence, missing evidence, or oldest unresolved item. Keyboard navigation between records is supported, but the next item must not be approved accidentally after a failed action. The inspection surface provides zoom, pan, fit-to-screen, image dimensions, and an optional comparison with the normalized derivative. Findings link to the relevant audit stage and policy version.

Approval is a confirmation of human review, not an acknowledgement of an AI pass. If the reviewer overrides a warning, the interface requires a reason and displays the resulting risk. Rejection requires a reason category and optional note. Re-audit explains whether the source, threshold, prompt, provider model, or previous failure caused the request. Metadata editing uses a draft and approved version distinction; unsaved edits must be recoverable or clearly discarded.

Packaging presents a preflight summary before finalization: file count, size, JPEG validity, color space, metadata verification, disclosure reminder, and output location label. A package failure leaves the decision intact and offers retry. Destructive actions require confirmation; retry and refresh actions should be safe to repeat.

## Affected blueprint areas
This applies to the workflow and state transition documents, review override policy, metadata versioning, finalization state machine, frontend inspection components, and API action contracts.

## Dependencies
The UX depends on stable audit evidence, idempotency keys, durable jobs, error taxonomy, accessible component behavior, and configured policy thresholds. It also depends on a clear distinction between hard blockers and advisory warnings.

## Acceptance criteria
- A reviewer can process a representative batch without opening a terminal.
- Every automated result includes understandable evidence and a next action.
- Approval, override, rejection, retry, and finalization are auditable.
- Partial failures preserve completed work and do not mislead the operator.
- Unsaved metadata and stale revisions are handled visibly.
- The workflow is operable with keyboard and screen-reader support.

## Risks / open questions
Too much evidence can slow high-volume review, while too little evidence undermines trust. The owner must select default triage ordering, decide whether batch approval is allowed, and define the minimum override note. The product also needs usability testing with real generated-image defects rather than synthetic happy paths.