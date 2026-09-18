# Frontend API Client Specification

## Purpose

This document defines the micro-specification for the frontend HTTP client responsible for all communication between the Next.js user interface and the FastAPI backend. The client encapsulates network logic, error handling, and request formatting so that UI components never interact with networking primitives directly.

## Status

PENDING

## Responsibilities

The API client module must fulfill the following responsibilities:

| Responsibility | Description |
|---|---|
| Base URL Configuration | Point all requests to the local backend server running on port 8000 |
| Upload Batch | Send multipart form data containing an array of image files |
| Fetch Records | Retrieve image records with optional status filtering via query parameters |
| Approve Single Record | Submit approval for one record using its identifier as a path parameter |
| Approve Multiple Records | Iterate over an array of record identifiers and submit sequential approval calls |

## Library Selection

The implementation should use either Axios or the native Fetch API. Whichever library is chosen, it must be wrapped in a centralized client module so that swapping libraries later does not affect component-level code.

## Endpoint Specifications

### Upload Batch

| Property | Value |
|---|---|
| HTTP Method | POST |
| Content Type | Multipart form data |
| Payload | Array of file objects selected by the user |
| Expected Response | Confirmation of queued records with generated identifiers |

### Fetch Records

| Property | Value |
|---|---|
| HTTP Method | GET |
| Query Parameters | Optional status filter accepting values: PENDING, AUDITING, PASSED, FLAGGED, READY |
| Expected Response | Array of record objects with metadata, status, and thumbnail paths |

### Approve Single Record

| Property | Value |
|---|---|
| HTTP Method | POST |
| Path Parameter | Record identifier embedded in the URL path |
| Expected Response | Updated record object reflecting READY status |

### Approve Multiple Records

| Property | Value |
|---|---|
| Execution Strategy | Sequential iteration over provided record identifiers |
| Underlying Call | Reuses the single-record approval endpoint per iteration |
| Completion Behavior | Resolves when all individual approvals have returned or when a failure halts the sequence |

## Error Handling Constraints

All network failures must be caught and transformed into user-friendly messages before reaching the UI layer. The client must never expose raw stack traces or HTTP status codes directly to end users.

| Error Category | User-Facing Message Pattern |
|---|---|
| Network unreachable | Inform the user that the backend service is not running |
| Timeout exceeded | Inform the user that the request took too long and suggest retrying |
| Server error response | Inform the user that an internal error occurred and provide a generic recovery suggestion |
| Malformed response | Inform the user that unexpected data was received |

## Timeout Configuration

Every request must enforce a maximum timeout duration. If the backend does not respond within this window, the client must abort the request and trigger the timeout error handling path. The timeout value should be configurable from a single constant at the top of the client module.

## Header Management

Content-Type headers must be set appropriately per endpoint. Multipart uploads must allow the browser to set the boundary automatically rather than hardcoding the header. JSON responses and requests must explicitly declare their content type. Any additional required headers such as Authorization must be attached centrally through request interceptors or wrapper functions.