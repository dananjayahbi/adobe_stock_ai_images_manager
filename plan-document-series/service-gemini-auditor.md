# Service Specification: Gemini Semantic Auditor

| Field | Value |
|---|---|
| Document ID | SVC-GEM-AUDIT-002 |
| Component | Semantic AI Audit Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Use the Gemini 2.5 Flash model to perform visual artifact detection and intellectual property screening that cannot be achieved through deterministic local heuristics. This service runs only after the QC engine passes an image, ensuring paid API calls are reserved for viable candidates.

## Responsibilities

| Responsibility | Description |
|---|---|
| Read Image Bytes | Load the target image file into memory as raw bytes suitable for multimodal API submission. |
| Construct Inspection Prompt | Build a natural language prompt requesting the model to inspect for anatomy defects (extra fingers, asymmetric features, impossible geometry), AI generation artifacts (unnatural textures, repeating patterns, melting boundaries), and IP/trademark violations (recognizable logos, copyrighted characters, branded products). |
| Enforce Structured Output | Instruct the model to return strict JSON containing a pass boolean, a confidence float between 0.0 and 1.0, and an issues array of strings. |
| Parse Response | Deserialize the JSON response body, extract the confidence score and issues list, and validate types before returning to the caller. |

## Configuration

| Parameter | Value | Rationale |
|---|---|---|
| Model | Gemini 2.5 Flash | Chosen for speed and cost efficiency on high-volume batch auditing. |
| Temperature | 0.1 | Near-deterministic output required for consistent pass/fail decisions across repeated evaluations of the same image. |
| Response MIME Type | application/json | Forces the model to emit parseable JSON rather than freeform markdown or prose. |

## Behavior

1. Receive the image path and read bytes into memory.
2. Assemble the multimodal request payload combining the image bytes and the constructed prompt.
3. Submit the request to the Gemini API with the specified configuration parameters.
4. Await the response within the defined timeout window.
5. Parse the returned JSON string into a native dictionary structure.
6. Validate that the confidence field is a float within the 0.0 to 1.0 range.
7. Validate that the issues field is a list of strings.
8. Return the parsed result to the orchestrator.

## Timeout and Retry Policy

| Scenario | Action |
|---|---|
| API call exceeds timeout | Abort the request, retry exactly once with a fresh connection. |
| Transient failure (HTTP 5xx, connection reset) | Retry exactly once after a brief backoff. |
| Persistent failure after retry | Return a flagged status with a descriptive error reason indicating the nature of the failure. Do not retry further. |
| Malformed JSON response | Treat as a persistent failure. Return flagged status with parsing error reason. |

## Constraints

- Never block the calling thread indefinitely. All API calls must have a hard timeout enforced at the transport layer.
- Retry at most once per invocation. Multiple retries risk cascading delays in the background task queue.
- On persistent failures, the service must return a structured flagged result rather than raising an exception. The orchestrator depends on receiving a valid response dictionary regardless of outcome.
- Image bytes must be read fully before submission; do not stream directly from disk to avoid file lock contention with other services.
- The prompt must not include any instructions that could cause the model to refuse the request or return safety-filtered empty responses for legitimate stock imagery.
| Field | Value |
|---|---|
| Document ID | SVC-GEM-AUDIT-002 |
| Component | Semantic AI Audit Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |