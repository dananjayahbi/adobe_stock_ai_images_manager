# Service Specification: Cross-Cutting Error Handling Strategy

| Field | Value |
|---|---|
| Document ID | SVC-ERR-007 |
| Component | Error Handling Strategy |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services (Cross-Cutting) |

## Purpose

Define consistent error behavior across all backend components in the Adobe Stock AI Image Studio. Every service, orchestrator, and API endpoint must follow these conventions to ensure predictable failure modes, debuggability, and graceful degradation under adverse conditions.

## Error Categories

| Category | Examples | Primary Impact |
|---|---|---|
| File I/O Errors | Corrupt uploads that cannot be decoded, disk full preventing writes, permission denied on directories, truncated files from interrupted uploads | QC engine failures, storage manager failures, thumbnail generation failures |
| API Errors | Gemini rate limit responses (HTTP 429), connection timeouts, malformed JSON responses, authentication token expiration, service outages | Semantic auditor failures, metadata generator failures |
| Process Errors | ExifTool binary not found on PATH, Tesseract OCR engine missing, subprocess killed by OS due to memory limits, incompatible binary versions | Metadata embedding failures, gibberish detection failures |
| Database Errors | SQLite database locked due to concurrent writers, unique constraint violations on record identifiers, foreign key violations during orphan cleanup, corrupted WAL files | Orchestrator state transition failures, record persistence failures |

## Core Strategy Principles

| Principle | Description |
|---|---|
| Structured Returns Over Exceptions | Every service returns structured error information as part of its normal output contract rather than raising unhandled exceptions that propagate unpredictably up the call stack. |
| Background Task Safety Net | All background tasks catch every exception type at the outermost boundary and transition the associated database record to FLAGGED status with a descriptive reason string. No background task may terminate without updating its record. |
| HTTP Status Code Consistency | API endpoints map internal error categories to appropriate HTTP status codes following REST conventions. Validation failures return 400, missing resources return 404, and unexpected internal errors return 500. |
| Frontend Resilience | Polling mechanisms on the frontend handle connection failures gracefully by displaying retry indicators rather than erroring silently or flooding the server with immediate re-requests. |

## HTTP Status Code Mapping

| Internal Condition | HTTP Status | Response Body Content |
|---|---|---|
| Invalid input parameters, missing required fields, unsupported file format | 400 Bad Request | Structured error object listing specific validation failures |
| Requested record identifier does not exist in database | 404 Not Found | Error object with resource type and requested identifier |
| File I/O failure during upload processing | 500 Internal Server Error | Generic error message; detailed cause logged server-side only |
| External API unavailable affecting request fulfillment | 503 Service Unavailable | Error object indicating which dependency is degraded |
| Database constraint violation or lock timeout | 500 Internal Server Error | Generic error message; detailed cause logged server-side only |

## Background Task Error Protocol

| Step | Action |
|---|---|
| 1 | Wrap entire task body in a broad exception handler at the outermost scope. |
| 2 | On catching any exception, extract the exception type and message into a human-readable reason string. |
| 3 | Open or reuse the task's dedicated database session. |
| 4 | Set the record status to FLAGGED. |
| 5 | Store the reason string in the record's error details or reasons field. |
| 6 | Commit the session to persist the state transition. |
| 7 | Close the session in a guaranteed cleanup block. |
| 8 | Log the full exception traceback at error level for developer diagnostics. |

## Service-Level Error Contracts

| Service | Error Return Format | Caller Responsibility |
|---|---|---|
| QC Engine | Dictionary with passed=false and populated reasons list | Orchestrator reads reasons and persists them to the record |
| Gemini Auditor | Dictionary with flagged status and error reason string | Orchestrator treats flagged as terminal for that pipeline stage |
| Gemini Metadata | Dictionary with empty title and keywords list plus error field | Orchestrator prevents progression to embedding stage |
| ExifTool Embedder | Boolean false plus logged stderr content | Orchestrator marks record as FLAGGED with embedding failure reason |
| Storage Manager | Structured error object with operation type and failure cause | Upload endpoint returns appropriate HTTP status to client |

## Degradation Matrix

| Dependency Unavailable | System Behavior | User Impact |
|---|---|---|
| Gemini API unreachable | Records transition to FLAGGED with API error reason | Images remain in inbox pending manual review or API restoration |
| ExifTool missing | Application fails at startup with clear error message | No uploads accepted until dependency resolved |
| Tesseract missing | QC engine skips gibberish check, logs warning | Reduced filtering capability but pipeline continues |
| SQLite locked | Orchestrator retries briefly then flags record | Potential delay in status updates visible to frontend |
| Disk full | Storage manager returns structured I/O error | Upload endpoint returns 500; existing records unaffected |

## Constraints

- No service may allow an unhandled exception to escape its public interface boundary. All exceptions must be caught internally and converted to structured error responses.
- Error reason strings stored in the database must be human-readable and actionable. Avoid raw stack traces in user-facing fields; reserve those for server logs.
- Logging must include sufficient context (record ID, file path, service name) to trace errors without requiring reproduction.
- Frontend polling intervals must implement exponential backoff on consecutive connection failures to prevent amplifying server load during outages.
- Error handling code paths must themselves be protected against secondary failures (e.g., if logging fails, the primary error response must still reach the caller).
| Field | Value |
|---|---|
| Document ID | SVC-ERR-007 |
| Component | Error Handling Strategy |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services (Cross-Cutting) |