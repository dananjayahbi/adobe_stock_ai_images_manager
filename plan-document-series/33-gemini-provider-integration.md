# 33 — Gemini Provider Integration

## Purpose
Define the boundary between the local studio and Gemini so multimodal auditing and metadata generation are reliable, replaceable, observable, and safe for a human-in-the-loop workflow. The integration must treat the provider as an external dependency rather than allowing SDK behavior to leak into domain state.

## Scope
This document covers provider abstraction, authentication, model selection, request construction, image transport, timeouts, configuration, dependency health, and provider error translation. It covers semantic audit and metadata-generation calls but not their prompt or response schemas, which are defined in documents 34 and 35.

## Decisions / requirements
The backend shall expose an internal provider interface with separate operations for semantic auditing and metadata generation. Domain services receive an image artifact reference and an immutable request context; they do not call the Gemini SDK directly. The adapter selects the configured model, API endpoint, generation settings, and response mode from versioned configuration. The initial model may be Gemini 2.5 Flash, but model identifiers must remain configurable and recorded for every call.

Authentication uses a server-side API credential loaded from environment or protected local configuration. Credentials must never be returned through API responses, written to ordinary logs, embedded in prompts, or stored with audit evidence. Startup health checks may report that a credential is configured without revealing its value. If no credential is available, the application must remain usable for deterministic QC and manual review while marking provider-dependent stages unavailable.

Requests use the normalized JPEG derivative selected by the pipeline, not an arbitrary user path. The adapter sets an explicit MIME type, bounded payload size, low temperature appropriate to the operation, structured JSON response expectations, and a request timeout. Image bytes are read once per call, with memory and duration limits. Provider calls are performed by bounded workers and are never made from a request handler that can hold a database transaction open.

The adapter translates authentication failures, invalid requests, quota exhaustion, transient transport errors, malformed responses, and provider safety refusals into the shared error taxonomy. It returns typed success or failure evidence, including model, request identifier when available, elapsed duration, and provider status category. Provider responses are not trusted until documents 34–36 validate them.

## Affected blueprint areas
This refines `gemini_service.py`, the Stage 2 semantic audit, Stage 3 metadata generation, configuration, background processing, and diagnostic boundaries in the blueprint. It also constrains API and job behavior in documents 37–39 and 49.

## Dependencies
It depends on documents 03, 10, 12, 25, 27, 29, 33–38, and the provider’s current official SDK and service documentation. Local normalization and content hashing must complete before an external request is dispatched.

## Acceptance criteria
- Semantic and metadata calls use an injectable provider adapter.
- Model, configuration, timeout, and artifact hash are recorded per call.
- Missing credentials produce a clear degraded state rather than a crash or false pass.
- Secrets are absent from logs, responses, and persisted evidence.
- Every provider error maps to a retryable, terminal, or review-required category.
- Calls are bounded by configured payload, timeout, and concurrency limits.

## Risks / open questions
Gemini SDK response and authentication behavior may change between versions. Provider retention and training-use terms require an explicit privacy decision. The owner must choose whether a future second provider is an MVP requirement or only an adapter-ready design goal. Network availability on a local desktop is also not guaranteed, so offline review behavior must remain useful.