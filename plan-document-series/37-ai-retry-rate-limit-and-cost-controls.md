# 37 — AI Retry, Rate-Limit, and Cost Controls

## Purpose
Control external AI latency, spend, quota usage, and duplicate work while providing deterministic recovery for transient provider failures and preserving the human review path.

## Scope
This document covers retry classification, backoff, quotas, concurrency, caching, budgets, request deduplication, cancellation, and degraded behavior for semantic and metadata calls. It does not define provider response schemas or approval rules.

## Decisions / requirements
Retries are allowed only for explicitly transient conditions such as connection resets, timeouts, temporary service errors, and documented rate limits. Authentication errors, invalid requests, unsupported media, policy refusals, malformed successful responses, and content-risk findings are not blindly retried. Backoff uses bounded exponential delays with jitter, a maximum attempt count, and a total elapsed-time limit. Retry state is durable so process restarts do not reset an unlimited loop.

Each call has a deduplication key derived from operation type, normalized artifact hash, prompt version, model configuration, and policy context. A completed valid result may be reused when the key matches and its freshness policy permits. Cache reuse must preserve provenance and must not hide that the result was generated under an older model or policy. Invalid results are never cached as success.

Concurrency is bounded globally and per operation. The system has configurable daily or session budgets for request count, estimated tokens or image calls, and monetary spend when provider pricing is available. Budget exhaustion pauses new provider work and marks items provider-blocked or review-required; deterministic QC and manual actions remain available. User-visible diagnostics show category and remaining budget without exposing credentials.

Cancellation prevents queued calls and requests cooperative cancellation for active calls where supported. A cancelled request must not later overwrite a newer audit or metadata edit. Batch processing isolates failures so one rate-limited item does not erase successful results. The system records attempt number, delay category, provider status, estimated cost, and final outcome.

## Affected blueprint areas
This refines background auditing, metadata generation during approval, configuration, error taxonomy, durable jobs, and dashboard progress. It informs documents 12, 25, 33, 37–39, 44, and 49.

## Dependencies
It depends on provider adapter behavior, durable job records, artifact hashes, configuration management, observability, and the human-review policy. Pricing and quota semantics must be verified against current provider terms.

## Acceptance criteria
- Only classified transient failures are retried.
- Backoff, attempts, and total time are bounded and persisted.
- Duplicate requests are avoided through a provenance-aware key.
- Concurrency and budgets are enforceable under batch load.
- Cancellation prevents stale results from changing current state.
- Provider exhaustion leaves a clear manual-review or retry path.

## Risks / open questions
Provider pricing and quota headers may be unavailable or change without notice. Caching may preserve an answer that is no longer policy-compliant. The owner must select default budgets, cache retention, whether metadata calls may be retried after user approval begins, and how estimated cost is displayed when exact billing is unknown.