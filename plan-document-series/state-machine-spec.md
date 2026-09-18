# Image Record Lifecycle State Machine Specification

## Purpose

This document formally defines the state machine governing image record lifecycles from initial upload through final approval. It specifies all valid states, permitted transitions, trigger conditions, side effects, and explicitly forbidden paths.

## Status

PENDING

## State Definitions

| State | Description |
|---|---|
| PENDING | Record has just been uploaded and is awaiting processing initiation |
| AUDITING | Background task is actively running quality control checks on the image |
| PASSED | All automated heuristic and semantic checks succeeded; awaiting human review |
| FLAGGED | One or more automated checks failed or returned low confidence; requires human decision |
| READY | Record has been approved, metadata has been embedded, and the file is staged for upload to Adobe Stock |

## Valid Transitions

Each transition is defined by its source state, target state, trigger condition, and resulting side effects.

### PENDING to AUDITING

| Property | Value |
|---|---|
| Trigger | Automatic upon successful upload completion |
| Initiator | System (no human action required) |
| Side Effects | Background task enqueued for quality control processing; timestamp recorded for audit start |

### AUDITING to PASSED

| Property | Value |
|---|---|
| Trigger | Both heuristic analysis and semantic analysis return passing results |
| Initiator | System (automated evaluation completion) |
| Side Effects | Quality scores stored on the record; thumbnail confirmed available; record surfaces in the passed queue for human review |

### AUDITING to FLAGGED

| Property | Value |
|---|---|
| Trigger | Any single quality control check fails or returns confidence below the acceptable threshold |
| Initiator | System (automated evaluation completion) |
| Side Effects | Failure reasons recorded on the record; specific check identifiers logged; record surfaces in the flagged queue requiring human attention |

### PASSED to READY

| Property | Value |
|---|---|
| Trigger | Human reviewer clicks approve on the individual record or includes it in a bulk approval action |
| Initiator | Human operator |
| Side Effects | Final metadata embedding executed via ExifTool; file moved or marked as staged for upload; approval timestamp recorded; record moves to the ready view |

### FLAGGED to READY

| Property | Value |
|---|---|
| Trigger | Human reviewer overrides the automated flag and explicitly approves the record |
| Initiator | Human operator |
| Side Effects | Override reason optionally recorded; final metadata embedding executed via ExifTool; file moved or marked as staged for upload; approval timestamp recorded; record moves to the ready view |

## Invalid Transitions

The following transitions are explicitly forbidden and must be rejected by the backend if attempted:

| Forbidden Transition | Reason |
|---|---|
| READY to any earlier state | Once approved and staged, the record is considered finalized; reverting would cause metadata inconsistency and staging conflicts |
| PENDING to READY | Skipping auditing violates the quality assurance pipeline; no record may reach ready status without passing through automated checks |
| PENDING to PASSED | Automated checks must run before a pass determination can be made |
| PENDING to FLAGGED | Automated checks must run before a flag determination can be made |
| PASSED to AUDITING | Re-auditing a passed record is not supported in the current lifecycle model |
| FLAGGED to AUDITING | Re-auditing a flagged record is not supported; human override is the only exit path |
| FLAGGED to PASSED | A flagged record cannot become passed without human intervention; the flag indicates automated uncertainty |
| READY to PENDING | Complete reversal is not supported; new uploads create new records |

## State Transition Diagram Summary

```
PENDING --> AUDITING --> PASSED --> READY
                 |                    ^
                 +--> FLAGGED --------+
```

## Transition Enforcement

| Enforcement Layer | Responsibility |
|---|---|
| Database model | State field constrained to the five defined values |
| API endpoints | Each mutation endpoint validates that the current state permits the requested transition before executing |
| Background tasks | Audit worker only processes records currently in PENDING state and transitions them atomically |
| Frontend actions | Approval buttons only rendered for records in PASSED or FLAGGED states |

## Side Effect Guarantees

All side effects associated with a transition must execute atomically with the state change. If a side effect fails (for example, ExifTool crashes during metadata embedding), the state transition must not persist. The record should remain in its prior state and the failure should be logged for investigation.