# Service Specification: Background Audit Orchestrator

| Field | Value |
|---|---|
| Document ID | SVC-ORCH-005 |
| Component | Background Task Orchestration Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Coordinate all QC pipeline stages asynchronously after an image upload completes. The orchestrator manages database session lifecycle, invokes services in sequence, evaluates results against business thresholds, and ensures every record reaches a terminal status regardless of success or failure along the path.

## Responsibilities

| Responsibility | Description |
|---|---|
| Accept Invocation Parameters | Receive a record identifier and a database factory callable from the upload endpoint or task scheduler. |
| Manage Session Lifecycle | Open a new dedicated database session using the provided factory. Commit changes and close the session in all exit paths. |
| Transition to Auditing | Set the record status to AUDITING immediately upon session open and commit this change before invoking any services. |
| Invoke Deterministic QC | Call the QC engine service with the image path associated with the record. |
| Persist Heuristic Results | Update the database record with computed megapixels, Laplacian variance, and the full heuristic breakdown from the QC engine. |
| Evaluate QC Outcome | If the QC engine reports failure, transition the record to FLAGGED with the provided reasons and terminate the pipeline. |
| Invoke Semantic Auditor | If QC passes, call the Gemini auditor service for visual artifact and IP screening. |
| Evaluate Confidence | Compare the auditor confidence score against the 0.75 threshold to determine PASSED or FLAGGED status. |
| Handle Exceptions | Catch all exceptions at the orchestration level, transition the record to FLAGGED with a descriptive error message, and ensure session cleanup. |

## Pipeline Flow

| Stage | Input | Service Called | Success Transition | Failure Transition |
|---|---|---|---|---|
| 1 - Initialize | record_id, db_factory | None | Status set to AUDITING, committed | Exception caught, status set to FLAGGED |
| 2 - Deterministic QC | Image path from record | QC Engine | Record updated with metrics, proceed to Stage 3 | Status set to FLAGGED with reasons, pipeline terminates |
| 3 - Semantic Audit | Image path from record | Gemini Auditor | Proceed to Stage 4 | Status set to FLAGGED with API error reason, pipeline terminates |
| 4 - Confidence Gate | Auditor confidence score | None (local evaluation) | Status set to PASSED if confidence >= 0.75 | Status set to FLAGGED if confidence < 0.75 |
| 5 - Finalize | Current record state | None | Session committed and closed | Session committed and closed |

## Confidence Threshold

| Parameter | Value | Rationale |
|---|---|---|
| Minimum Confidence | 0.75 | Scores at or above this threshold indicate the Gemini auditor has sufficient certainty that the image contains no disqualifying artifacts or IP violations. Scores below require human review. |

## Constraints

- Each background task invocation must create its own database session. Sessions must never be shared across threads or concurrent tasks to prevent transaction isolation violations and SQLite locking errors.
- The database factory callable pattern ensures the orchestrator remains decoupled from session creation logic and can work with both production and test configurations.
- Always commit the AUDITING status before invoking external services. If the process crashes mid-audit, the record will not remain stuck in PENDING state.
- Graceful degradation is mandatory when Gemini is unavailable. Network timeouts, rate limits, or authentication failures must result in a FLAGGED status with a descriptive API error reason rather than an unhandled exception or infinite retry loop.
- The orchestrator must never leave a session open. Use guaranteed cleanup patterns to ensure the session closes even when exceptions occur during service invocations.
- All status transitions must be persisted to the database immediately via commit before proceeding to the next stage. This provides crash recovery visibility.
- The orchestrator does not invoke the metadata generator or ExifTool embedder directly. Those services are triggered separately after a record reaches READY status through the approval workflow.
| Field | Value |
|---|---|
| Document ID | SVC-ORCH-005 |
| Component | Background Task Orchestration Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |