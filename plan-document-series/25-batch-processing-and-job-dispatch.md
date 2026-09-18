# 25 — Batch Processing and Job Dispatch

## Purpose
Define durable processing orchestration for validation, normalization, thumbnails, deterministic QC, optional AI review, metadata, and packaging without overwhelming local resources or losing work on restart.

## Scope
The plan covers job creation, queues, worker limits, ordering, retries, cancellation, progress, backpressure, and restart recovery. It excludes individual detector algorithms and provider prompt content.

## Decisions / requirements
Each processing stage is represented by a durable job linked to an asset, batch, input hash, policy version, and attempt. Jobs are claimed transactionally with a lease or equivalent ownership marker and heartbeat. A worker must verify that its input and expected asset version remain current before committing results. Stale or duplicated workers cannot overwrite newer evidence.

The default stage order is safe intake, validation, normalization, thumbnail generation, deterministic QC, semantic audit when eligible, metadata generation after approval, embedding, verification, and ready export. Technical hard failure can stop paid work, while warnings remain visible. Jobs must be independently retryable and must not rerun completed stages unless the input or configuration changed.

Concurrency is bounded separately for CPU-heavy image work, OCR, external provider calls, and ExifTool operations. The dispatcher applies backpressure based on memory, queue depth, provider rate limits, and user cancellation. Batch progress reports item counts by state and stage, not a single misleading percentage. A batch may continue after one item fails, with isolation and a final summary.

Retry policy distinguishes transient file locks, process failures, provider rate limits, and terminal invalid content. Exponential backoff has caps and an operator-visible retry count. Cancellation stops queued work and requests cooperative termination for running work; cleanup follows the filesystem plan. On restart, expired leases are recovered after checking temporary files and database evidence.

## Affected blueprint areas
This refines the blueprint’s background processing assumptions, API endpoints, dashboard progress, QC stages, Gemini calls, OCR, ExifTool, and storage lifecycle.

## Dependencies
It depends on status transitions, error taxonomy, database transactions, filesystem atomicity, provider limits, and configuration of worker counts and timeouts.

## Acceptance criteria
- Jobs survive process restarts without duplicate authoritative results.
- Concurrency is bounded by stage and configurable.
- Partial batches continue safely and report item-level failures.
- Cancellation and retries do not delete originals or bypass approval.
- Stale workers are rejected through version or lease checks.
- Progress is durable, stage-aware, and reconcilable.

## Risks / open questions
The project must choose an in-process queue or a local durable queue implementation. SQLite write contention may constrain workers. External tools may not terminate cleanly on Windows. Whether AI audits run automatically for all technically passing images or require reviewer initiation remains unresolved.