# 21 — Upload API and Batch Ingestion

## Purpose
Define safe, observable multipart ingestion for individual files and batches, including limits, partial success, duplicate handling, and progress semantics.

## Scope
The contract covers upload request validation, batch creation, streaming to temporary storage, per-item outcomes, resumability, and client-visible progress. It excludes image normalization, QC algorithms, and frontend styling.

## Decisions / requirements
An ingestion request creates or references a batch with an idempotency key, client label, creation time, and policy context. Each multipart item is processed independently after request-level checks. The service must enforce configurable file-count, request-size, per-file-size, filename-length, and upload-duration limits before accepting unbounded data. Bytes stream to a controlled temporary location rather than memory-only buffers.

The response distinguishes accepted, duplicate, rejected, and failed items. Accepted items receive stable asset identifiers and a processing status. A malformed item does not roll back valid files in the same batch. If the connection ends after storage, a reconciliation or resume mechanism identifies the completed item rather than creating a second source. The API must not report success until the source bytes have been flushed, hashed, and registered durably.

Filenames are normalized for display and stored separately from safe internal names. Content type headers are advisory; actual validation belongs to document 22. Upload progress measures bytes received and durable registration, while processing progress is reported by jobs and must not be conflated with network progress. A batch summary reports counts and links to item-level errors.

Duplicate behavior is explicit: the default is to retain the original asset and return a duplicate reference, with an option to associate the occurrence to the new batch without reprocessing. User-selected reprocessing must still preserve source identity and history. Upload cancellation removes only incomplete temporary data after safe cleanup; it cannot remove an already registered source.

## Affected blueprint areas
This refines the multipart POST, drag-and-drop intake, batch counter, inbox storage, database registration, and status reporting in the blueprint. It feeds documents 22, 25, 26, 45, 46, 49, and 51.

## Dependencies
The contract depends on idempotency and hashing, file safety, durable jobs, filesystem atomicity, API error schemas, and local-access controls.

## Acceptance criteria
- Limits are enforced before unbounded resource use.
- Partial batch outcomes are explicit and queryable.
- A completed upload is durable before success is reported.
- Retries and interrupted connections do not duplicate sources.
- Content-type spoofing and unsafe filenames cannot bypass validation.
- Progress and errors are attributable to individual items.

## Risks / open questions
The maximum practical batch size and resumable-upload requirement are unresolved. Multipart handling may be affected by reverse proxies or packaged desktop servers. The UI must decide whether duplicate items are visually grouped or listed separately. Whether uploads can continue while processing is active requires worker-capacity decisions.