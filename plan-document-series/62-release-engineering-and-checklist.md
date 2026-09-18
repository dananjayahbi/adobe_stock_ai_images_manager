# 62 — Release Engineering and Checklist

## Purpose
Provide a repeatable release process that turns a tested repository state into a traceable Windows distribution and prevents incomplete, unsafe, or policy-stale functionality from being shipped.

## Scope
The release process covers versioning, dependency lock state, build artifacts, database migrations, quality gates, security and accessibility review, documentation, signing, packaging, rollout, rollback, and release evidence. It excludes long-term product prioritization.

## Decisions / requirements
Every release has a version, source revision, build environment, dependency snapshot, policy baseline version, model and prompt versions, and generated artifact checksums. Changes to thresholds, prompts, schemas, migrations, native tools, and installer behavior are called out separately because they can alter acceptance outcomes or recovery procedures. Release notes must distinguish user-visible behavior, operational changes, known limitations, and required user action.

The checklist begins with scope and risk review, then runs formatting and static checks, unit tests, integration and migration tests, AI evaluation, E2E smoke, accessibility checks, load smoke, and security scans. The release candidate is installed on a clean supported Windows machine and upgraded from the prior supported release. The packaged application must verify dependencies, create safe data directories, and start successfully without development-only assumptions.

Release approval requires zero unresolved critical defects, documented disposition for lower-severity risks, current policy verification, successful source preservation and package verification, and review of logs for secrets. Artifacts are retained with bounded, access-controlled evidence. If a check is skipped, the reason, owner, and follow-up date are recorded; skipped validation is never represented as passed.

Rollout begins with a small internal or controlled user group when practical. Monitoring focuses on startup, migrations, processing failures, provider errors, storage growth, and package verification. Rollback means restoring a previous application version without overwriting user data and following the documented migration recovery path; irreversible schema changes require explicit planning before release.

## Affected blueprint areas
This governs the full technology stack, tests 55–60, Windows packaging, migrations, observability, policy calibration, AI provenance, and operational documents 63–66.

## Dependencies
It depends on CI or an equivalent reproducible build process, signing credentials, clean Windows test machines, release artifact storage, migration backups, and owners for policy and security sign-off.

## Acceptance criteria
- A release candidate passes all required quality gates with evidence.
- Artifacts are reproducible or differences are documented and reviewable.
- Clean install and supported upgrade succeed.
- Version, policy, model, prompt, and dependency provenance is recorded.
- Rollback and data-preservation steps are tested or explicitly risk-accepted.
- Known issues and operator actions are published with the release.

## Risks / open questions
Native dependency packaging and code signing may become schedule blockers. The team must choose a versioning scheme, release cadence, artifact retention period, CI platform, approvers, and the minimum safe rollout size for a single-user desktop product.