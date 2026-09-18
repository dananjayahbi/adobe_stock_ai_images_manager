# Backend API - Records Endpoint Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - REST Endpoint |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Define the record listing endpoint that allows clients to retrieve image records from the database with optional filtering, pagination, and sorting. This endpoint powers the main dashboard grid view in the frontend application.

## Responsibilities

### Endpoint Definition

| Property | Value |
|---|---|
| HTTP Method | GET |
| URL Path | /api/records |
| Content Type | application/json |
| Response Schema | RecordListResponse |
| Success Status Code | 200 OK |

### Query Parameters

The endpoint accepts the following optional query parameters:

| Parameter Name | Type | Required | Default | Description |
|---|---|---|---|---|
| status | String | No | None (all statuses) | Filter results to a specific pipeline state; must be one of PENDING, AUDITING, PASSED, FLAGGED, READY |
| limit | Integer | No | 100 | Maximum number of records to return in a single response |
| offset | Integer | No | 0 | Number of records to skip before returning results; used for pagination |

### Processing Behavior

The endpoint must execute the following sequence:

| Step | Action | Description |
|---|---|---|
| 1 | Validate query parameters | Ensure status is a valid enum value if provided; ensure limit and offset are non-negative integers |
| 2 | Enforce limit bounds | Cap the limit parameter at the maximum allowed value even if the client requests more |
| 3 | Build database query | Construct a query against the ImageRecord table with the status filter applied as a WHERE clause when present |
| 4 | Apply sorting | Order all results by the created_at column in descending order so newest records appear first |
| 5 | Apply pagination | Use the offset and limit values to restrict the result set to the requested page |
| 6 | Execute query | Run the query within a read-only database session |
| 7 | Serialize results | Convert each ORM object to a RecordDetail schema instance |
| 8 | Count total matches | Determine the total number of records matching the filter regardless of pagination for UI display |
| 9 | Return response | Build and return a RecordListResponse containing the serialized records and total count |

### Error Handling

| Error Condition | HTTP Status | Response |
|---|---|---|
| Invalid status value | 400 Bad Request | ErrorResponse indicating which values are accepted |
| Negative limit or offset | 400 Bad Request | ErrorResponse explaining that pagination values must be non-negative |
| Limit exceeds maximum | 400 Bad Request | ErrorResponse stating the maximum allowed batch size |
| Database connection failure | 500 Internal Server Error | ErrorResponse with generic failure message |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Default limit | When no limit parameter is provided, the endpoint returns at most 100 records |
| Maximum limit | The endpoint rejects any request where limit exceeds 500 to prevent excessive memory consumption |
| Empty result handling | When no records match the filter criteria, the endpoint returns an empty list with total_count zero rather than raising an error or returning a 404 status |
| Descending chronological order | Results are always sorted by created_at descending; this ordering cannot be changed by the client |
| Status filter validation | Only the five defined status values are accepted; case-sensitive matching is enforced |
| Offset-based pagination | The system uses offset-based pagination rather than cursor-based; the frontend is responsible for calculating correct offset values |
| Read-only operation | This endpoint must never modify database state; it uses a session that does not permit writes |