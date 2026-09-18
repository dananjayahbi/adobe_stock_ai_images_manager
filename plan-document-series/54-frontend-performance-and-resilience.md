# 54 — Frontend Performance and Resilience

## Purpose
Define frontend performance and resilience expectations for a local review application handling large images, active background jobs, and batches that may contain hundreds of records. The interface should feel immediate without hiding work or consuming excessive memory.

## Scope
This plan covers loading strategy, image delivery, rendering, caching, polling, cancellation, offline-like provider outages, memory limits, and recovery after backend restarts. It excludes backend image-processing performance and provider optimization, which are addressed elsewhere.

## Decisions / requirements
The frontend should load the application shell quickly and defer noncritical inspection features until needed. Thumbnails are the default representation in queues; full-resolution files are fetched only for an explicit inspection action and are released when the viewer closes or changes record. Responsive image sizing, modern browser decoding, and bounded concurrency prevent a large batch from creating hundreds of full-size memory allocations. Object URLs and event listeners must be cleaned up reliably.

Queue rendering should use pagination or virtualization when record counts exceed the agreed threshold. Filters, sorting, and selection state must remain responsive while processing updates arrive. The client should debounce search and avoid refetching identical pages unnecessarily, but correctness takes priority over stale cache data after a decision or retry. Mutating actions invalidate or update affected records immediately and reconcile with the server response.

Progress uses durable job identity. Polling has a bounded interval, backoff after errors, and a stop condition when the job reaches a terminal state. If a connection fails, the UI explains that the backend may still be working and offers retry without duplicating the action. A reconnect or browser refresh restores batch context from server state. The client must never infer completion from elapsed time or a disappearing spinner.

Performance budgets should cover initial JavaScript, route transitions, time to first useful queue, thumbnail decode latency, and interaction delay on a representative Windows machine. Instrumentation records anonymized timing and client errors locally or through an opt-in diagnostics path. Accessibility behavior, especially focus and announcements, must not be sacrificed for virtualization or optimistic updates.

## Affected blueprint areas
This refines the Next.js dashboard, API client, thumbnail serving, background job progress, local deployment, and observability documents.

## Dependencies
It depends on pagination schemas, thumbnail contracts, durable jobs, browser support, storage access controls, and the chosen frontend data-fetching strategy. Representative image and batch fixtures are needed for measurement.

## Acceptance criteria
- The queue remains usable with the agreed maximum representative batch.
- Full-resolution images are not loaded for unseen records.
- Refresh and temporary backend loss recover without false completion.
- Polling stops or backs off appropriately and does not multiply after navigation.
- Browser memory and interaction budgets are measured on the supported Windows baseline.
- Performance optimizations preserve keyboard, screen-reader, and error behavior.

## Risks / open questions
Local file serving may dominate perceived latency. The team must set concrete budgets, choose virtualization thresholds, decide whether service-worker caching is appropriate, and determine whether diagnostics are retained beyond the local session. Large panoramas and malformed images need separate stress fixtures.