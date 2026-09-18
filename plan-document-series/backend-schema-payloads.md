# Backend Schema Payloads Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - Pydantic Schemas |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Define the Pydantic request and response schemas that validate all API contracts for the backend. These schemas enforce strict type safety at the boundary between HTTP requests and internal application logic, ensuring no malformed data reaches the pipeline.

## Responsibilities

### Schema Definitions

The following Pydantic models must be defined to cover all endpoint payloads:

#### UploadResponse

Returned by the batch upload endpoint after files are saved and records are created.

| Field Name | Type | Required | Description |
|---|---|---|---|
| uploaded_count | Integer | Yes | Number of files successfully accepted and persisted |
| record_ids | List of Integers | Yes | Database IDs of the newly created image records |

#### RecordDetail

Represents a single image record with all fields fully serialized. Used as the element type within list responses and as a standalone detail response.

| Field Name | Type | Required | Description |
|---|---|---|---|
| id | Integer | Yes | Primary key of the record |
| filename | String | Yes | Original filename |
| original_path | String | Yes | Filesystem path to the source image |
| thumbnail_path | String | Yes | Filesystem path to the generated thumbnail |
| status | String | Yes | Current pipeline state (PENDING, AUDITING, PASSED, FLAGGED, READY) |
| megapixels | Float | Yes | Computed resolution value |
| laplacian_variance | Float | Yes | Computed sharpness score |
| semantic_confidence | Float | Yes | AI confidence metric |
| heuristic_breakdown | Dictionary | Yes | Detailed audit check results; defaults to empty dictionary |
| failure_reasons | List of Strings | Yes | Human-readable failure explanations; defaults to empty list |
| title | String or Null | Yes | Generated or approved title; null if not yet assigned |
| keywords | List of Strings or Null | Yes | Generated or approved keywords; null if not yet assigned |
| created_at | Datetime string | Yes | ISO 8601 formatted UTC timestamp of creation |
| updated_at | Datetime string | Yes | ISO 8601 formatted UTC timestamp of last modification |

#### RecordListResponse

Returned by the records listing endpoint. Contains a collection of record detail objects.

| Field Name | Type | Required | Description |
|---|---|---|---|
| records | List of RecordDetail | Yes | Array of matching image records |
| total_count | Integer | Yes | Total number of records matching the filter before pagination |

#### ApproveResponse

Returned by the approval endpoint after a record is transitioned to READY state.

| Field Name | Type | Required | Description |
|---|---|---|---|
| status | String | Yes | The new status of the record (always READY on success) |
| title | String | Yes | The title embedded into the image metadata |
| keywords_count | Integer | Yes | Number of keywords embedded into the image metadata |

#### ErrorResponse

Standard error envelope returned for all HTTP error conditions.

| Field Name | Type | Required | Description |
|---|---|---|---|
| detail | String | Yes | Human-readable description of the error |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Strict type validation | All schemas must reject coercion; a string passed where an integer is expected must raise a validation error rather than silently converting |
| No extra fields allowed | Schemas must be configured to forbid any fields not explicitly defined in the specification; unexpected keys in request bodies trigger rejection |
| Datetime JSON serialization | All datetime fields must serialize to ISO 8601 strings in UTC; raw datetime objects must never appear in JSON output |
| Nullable field handling | Fields marked as nullable must accept explicit null values and omit-null behavior must be consistent across all schemas |
| Default values for collections | The heuristic_breakdown and failure_reasons fields must default to empty collections rather than null to simplify frontend consumption |
| Read-only response schemas | Response schemas are serialization-only; they must not accept input from request bodies unless explicitly designed as dual-purpose |