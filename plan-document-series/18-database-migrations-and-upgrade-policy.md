# 18 — Database Migrations and Upgrade Policy

## Purpose
Define how the local application evolves its SQLite schema while preserving image provenance, audit evidence, and user-created decisions.

## Scope
This document covers migration ownership, versioning, startup behavior, compatibility, backups, seed policy, rollback limits, and upgrade diagnostics. It does not select a particular migration library or describe implementation code.

## Decisions / requirements
Schema changes must be versioned, ordered, deterministic, and applied by an explicit migration runner. The application must refuse normal operation when the database is newer than the installed software, when a migration is missing, or when integrity checks fail. Startup should report the exact schema version and required action rather than silently creating or altering tables.

Migrations must be additive or data-preserving whenever practical. Renaming or splitting an image record requires a documented transformation that preserves source hashes, audit references, review decisions, state events, and export manifests. Destructive changes require an export or backup and explicit release approval. Historical policy versions and detector evidence must not be rewritten to fit a newer schema; compatibility adapters or versioned payload readers are preferred.

Before upgrade, the application should create a verified database backup and record its location, timestamp, schema version, and checksum. A failed migration must leave the prior database recoverable and must not claim completion. Rollback is supported by restoring the pre-upgrade backup, not by assuming every forward migration has a reverse operation. Filesystem data is backed up or reconciled separately because database and filesystem transactions are independent.

Fresh installations may receive controlled seed data such as default policy configuration, but seeds must be distinguishable from user data and must not create fake audits or decisions. Configuration defaults can be changed only through versioned policy or settings mechanisms. Upgrade diagnostics should identify blocked jobs, orphan files, stale exports, and records requiring manual repair.

## Affected blueprint areas
This governs the blueprint’s SQLite engine, application startup, configuration, storage lifecycle, diagnostics, and release process. It supports documents 17, 19, 20, 26, 64, 65, and 66.

## Dependencies
Migration planning depends on the logical schema, retention and backup policy, filesystem reconciliation, and supported desktop upgrade model. It also requires a chosen ORM and migration tool in document 08.

## Acceptance criteria
- Version compatibility and failure behavior are explicit.
- A pre-upgrade backup is created and verified before destructive risk.
- Interrupted migration cannot leave an ambiguous “upgraded” state.
- Historical evidence remains interpretable across versions.
- Fresh-install seeds are safe, minimal, and distinguishable.
- Upgrade tests cover representative old databases and interrupted operations.

## Risks / open questions
The project must decide whether automatic migrations run at startup or through an explicit maintenance action. Large evidence tables may make backups slow. SQLite file locking, antivirus interference, and Windows filesystem permissions can interrupt upgrades. The supported rollback window and backup retention period remain unresolved.