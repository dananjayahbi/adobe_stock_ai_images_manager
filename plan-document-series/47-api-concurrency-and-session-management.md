# 47 — API Concurrency and Session Management

## Purpose
Prevent lost updates, duplicate jobs, inconsistent state, and unsafe filesystem/database interactions when browser actions and workers operate concurrently.

## Scope
This document covers local operator sessions, transactions, optimistic concurrency, locks, worker access, action conflicts, and lifecycle of long-running requests. It does not define authentication controls or detailed route schemas.

## Decisions / requirements
Even a single-user desktop application must represent an actor and session context. The initial session may be a local operator session established at startup, but every mutating action records actor identity, session identifier, correlation identifier, and client revision. Session expiration and restart behavior must be explicit; stale sessions cannot silently continue after storage or configuration changes.

Database transactions are short and do not span provider calls, image processing, ExifTool execution, or network waits. Workers claim durable jobs with a lease, heartbeat, attempt number, and owner token. Claiming is atomic, and expired leases can be recovered without two active workers committing the same result. Filesystem operations use separate temporary and finalization protocols and are committed only after database state and artifact checks agree.

Mutating API actions use optimistic concurrency. The client sends the record or aggregate revision it inspected; a mismatch returns conflict with current status and a safe summary. Idempotency keys map repeated requests to their original result for a bounded retention period. State transitions are validated inside the transaction, not only in route code. A transaction that loses a race rolls back without deleting another worker’s artifacts.

Read endpoints may show slightly stale data but identify current revision and job state. Long operations return durable job identifiers rather than holding HTTP connections open. Cancellation requests set a durable cancellation marker; workers check it between stages and before commit. Session and worker diagnostics never include secrets or arbitrary local paths.

## Affected blueprint areas
This clarifies SQLite sessions, background audit tasks, approval/finalization routes, durable jobs, storage atomicity, and dashboard polling. It supports documents 16, 19, 25–26, 44–49.

## Dependencies
It depends on database schema and migration policy, job dispatch, filesystem atomicity, API schemas, local deployment, and security controls. SQLite locking and Windows file semantics require integration testing.

## Acceptance criteria
- Provider and filesystem work never holds an open database transaction.
- Jobs have atomic claims, leases, recovery, and commit guards.
- Concurrent edits return conflicts rather than overwriting newer decisions.
- Repeated mutating requests are idempotent where specified.
- Cancellation prevents stale work from committing current state.
- Every action is attributable to a session and actor.

## Risks / open questions
SQLite write contention may limit throughput for large batches. Lease recovery can race with a slow worker unless fencing tokens are enforced. The owner must choose session expiration, job lease duration, and whether the MVP supports more than one browser or local operator at a time.