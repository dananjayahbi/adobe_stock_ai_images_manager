# Backend API - Approve Endpoint Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - REST Endpoint |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Define the single-record approval endpoint that transitions an audited image from PASSED or FLAGGED state to READY state. This endpoint orchestrates metadata generation, file relocation, and EXIF embedding as a coordinated sequence of operations.

## Responsibilities

### Endpoint Definition

| Property | Value |
|---|---|
| HTTP Method | POST |
| URL Path | /api/records/{record_id}/approve |
| Content Type | application/json |
| Path Parameter | record_id (integer) |
| Response Schema | ApproveResponse |
| Success Status Code | 200 OK |

### Processing Behavior

The endpoint must execute the following sequence when invoked:

| Step | Action | Description |
|---|---|---|
| 1 | Fetch record by ID | Query the database for the ImageRecord matching the provided record_id path parameter |
| 2 | Handle missing record | If no record exists with the given ID, return a 404 Not Found response immediately |
| 3 | Check idempotency | If the record status is already READY, skip all processing and return a success response with the existing title and keyword count |
| 4 | Validate current status | Ensure the record is in either PASSED or FLAGGED state; any other state indicates an invalid transition attempt |
| 5 | Generate metadata | Invoke the metadata generation service to produce a title and keyword list optimized for Adobe Stock discoverability |
| 6 | Copy file to upload directory | Move the image file from the inbox directory to the ready_to_upload directory using a copy operation rather than a move to preserve the original until embedding succeeds |
| 7 | Embed metadata via ExifTool | Invoke the ExifTool embedding service to write the generated title and keywords into the image file's EXIF/IPTC fields in the ready_to_upload directory |
| 8 | Handle ExifTool failure | If the embedding step fails, delete the copied file from the ready_to_upload directory and return an error without updating the record status |
| 9 | Update record fields | Set the record status to READY, store the generated title, and store the generated keywords on the record |
| 10 | Commit transaction | Persist all changes to the database within a single transaction |
| 11 | Return response | Build and return an ApproveResponse containing the new status, the assigned title, and the count of embedded keywords |

### Error Handling

| Error Condition | HTTP Status | Response |
|---|---|---|
| Record not found | 404 Not Found | ErrorResponse indicating the record_id does not exist |
| Invalid status transition | 400 Bad Request | ErrorResponse explaining the record is in PENDING or AUDITING state and cannot be approved yet |
| Metadata generation failure | 502 Bad Gateway | ErrorResponse indicating the AI metadata service was unavailable or returned an error |
| File copy failure | 500 Internal Server Error | ErrorResponse indicating a filesystem issue; no database changes are committed |
| ExifTool embedding failure | 500 Internal Server Error | ErrorResponse indicating the embedding tool failed; the copied file is rolled back and the record remains in its previous state |
| Database commit failure | 500 Internal Server Error | ErrorResponse with generic failure message |

### Idempotency Contract

This endpoint is designed to be safely retried. The idempotency behavior is defined as follows:

| Current Record Status | Behavior on Repeated Call |
|---|---|
| READY | Return success immediately with existing title and keywords_count; perform no file operations or database writes |
| PASSED | Execute full approval pipeline |
| FLAGGED | Execute full approval pipeline (human override of automated flag) |
| PENDING | Reject with 400 error; audit has not completed |
| AUDITING | Reject with 400 error; audit is still in progress |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Idempotent for READY records | The endpoint checks status before performing any work; already-approved records produce no side effects |
| Human override for FLAGGED | Records in FLAGGED state may be approved by a human operator who has reviewed the failure_reasons and determined the image is acceptable despite automated flags |
| Rollback on ExifTool failure | If metadata embedding fails after the file has been copied, the system must delete the partially processed file from the ready_to_upload directory to prevent orphaned files |
| Copy then embed | The file is copied to the destination before ExifTool modifies it; the original in the inbox is preserved until the entire pipeline succeeds |
| Atomic database update | The status change, title assignment, and keyword storage must occur in a single database transaction; partial updates are not permitted |
| Single record scope | Each invocation processes exactly one record; batch approval is not supported through this endpoint |
| Metadata service dependency | The endpoint depends on an external metadata generation service; if that service is unavailable, the approval fails cleanly without modifying the record |