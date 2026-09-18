# Backend API - Upload Endpoint Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - REST Endpoint |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Define the batch upload endpoint that accepts multiple image files from the client, persists them to the inbox directory, creates corresponding database records, and triggers asynchronous auditing for each uploaded file.

## Responsibilities

### Endpoint Definition

| Property | Value |
|---|---|
| HTTP Method | POST |
| URL Path | /upload |
| Content Type | multipart/form-data |
| Request Body | List of files under a single form field |
| Response Schema | UploadResponse |
| Success Status Code | 200 OK |

### Processing Behavior

The endpoint must execute the following sequence for each request:

| Step | Action | Description |
|---|---|---|
| 1 | Validate batch size | Reject the entire request if the number of files exceeds the maximum batch limit |
| 2 | Iterate files | Process each uploaded file in the order received |
| 3 | Validate extension | Check that each file has an allowed extension before writing to disk |
| 4 | Resolve filename conflicts | If a file with the same name already exists in the inbox directory, append a timestamp suffix to the new filename to prevent overwrites |
| 5 | Save to inbox | Write the file bytes to the configured inbox storage directory |
| 6 | Generate thumbnail | Create a thumbnail image synchronously during the request cycle and save it to the thumbnails directory |
| 7 | Create database record | Insert a new ImageRecord with status set to PENDING, storing the original path and thumbnail path |
| 8 | Commit transaction | Persist all new records to the database within a single transaction |
| 9 | Dispatch background tasks | For each newly created record, schedule an asynchronous audit task to run outside the request-response cycle |
| 10 | Collect identifiers | Gather the database IDs of all successfully created records |
| 11 | Return response | Build and return an UploadResponse containing the count of uploaded files and the list of record IDs |

### Error Handling

| Error Condition | HTTP Status | Response |
|---|---|---|
| Batch size exceeds maximum | 400 Bad Request | ErrorResponse with detail explaining the limit |
| Invalid file extension | 400 Bad Request | ErrorResponse listing which files had disallowed extensions |
| No files provided | 400 Bad Request | ErrorResponse indicating empty upload |
| Database write failure | 500 Internal Server Error | ErrorResponse with generic failure message; any partially saved files should be cleaned up |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Allowed file extensions | Only .jpg and .jpeg files are accepted; validation is case-insensitive and occurs before any disk writes |
| Duplicate filename handling | When a collision is detected in the inbox directory, the system appends an underscore followed by a Unix timestamp before the file extension |
| Maximum batch size | No more than 50 files may be submitted in a single request; this limit is checked before processing begins |
| Synchronous thumbnail generation | Thumbnails must be generated within the request handler before returning, ensuring the UI can immediately display them |
| Asynchronous audit dispatch | The quality audit pipeline runs as a background task so the HTTP response is not blocked by potentially slow AI analysis |
| Atomic database commit | All records for a batch must be committed in a single transaction; partial inserts are not permitted |
| File cleanup on failure | If the database commit fails after files have been written to disk, the endpoint must remove the orphaned files from the inbox and thumbnails directories |