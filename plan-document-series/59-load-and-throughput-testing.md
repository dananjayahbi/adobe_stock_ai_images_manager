# 59 — Load and Throughput Testing

## Purpose
Measure whether the local studio can process realistic batches within acceptable time, memory, storage, and provider-cost bounds while maintaining correctness and review responsiveness.

## Scope
The plan covers upload throughput, thumbnail generation, deterministic QC, job queue behavior, database contention, API pagination, frontend queue rendering, package finalization, provider rate limits, and recovery under load. It does not promise cloud-scale multi-tenant performance.

## Decisions / requirements
Workload models must represent the intended operator rather than an arbitrary benchmark. At minimum, tests include a small interactive batch, the initial queue example of approximately 50 files, a larger stress batch, mixed image dimensions, duplicates, invalid files, and varying semantic-review policies. Scenarios record file sizes, megapixels, expected stage mix, concurrency, and whether the provider is fake or rate-limited.

Measurements include upload completion, time to first reviewable item, batch completion, per-stage latency, queue depth, retry count, SQLite lock or transaction waits, CPU, memory, temporary storage, thumbnail size, and provider requests, tokens, or cost estimates. Frontend measures interaction delay and memory while scrolling and inspecting. Results must distinguish cold start, warm cache, native-tool availability, and provider latency.

The system must preserve invariants under load: no duplicate logical records, no source overwrite, no false READY state, bounded retries, and complete event history. Backpressure is explicit. The queue should limit concurrent CPU-heavy work, provider requests, and package operations independently where necessary. Rate limits and cost budgets stop or defer work with a visible explanation rather than causing uncontrolled retries.

Load tests run on the supported Windows baseline with a clean environment and documented machine characteristics. Results are compared with budgets and prior releases; regressions require triage. The test harness must clean generated files and protect real user storage.

## Affected blueprint areas
This informs batch ingestion, job dispatch, filesystem atomicity, database indexing, thumbnail serving, provider controls, frontend resilience, observability, and documents 21, 25, 26, 37, 49, and 54.

## Dependencies
It depends on final workload targets, durable queue design, representative fixtures, metrics instrumentation, and a safe isolated environment. Provider load must comply with quota and cost controls.

## Acceptance criteria
- The representative batch completes within agreed interactive and processing budgets.
- Peak memory, CPU, storage, and provider usage remain bounded.
- Pagination and review remain responsive during background processing.
- Backpressure prevents uncontrolled work and preserves correctness.
- Restart or cancellation under load leaves recoverable state.
- Results are reproducible enough to compare releases and explain variance.

## Risks / open questions
A single Windows workstation may vary widely in CPU, disk, and antivirus behavior. The owner must set concrete budgets, choose the supported hardware baseline, decide maximum batch size, and determine whether load tests may use live provider quotas or only a substitute.