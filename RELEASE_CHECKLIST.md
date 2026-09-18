# Studio release checklist

This project is a local Windows review workstation. A release is not a claim of Adobe Stock acceptance.

## Required evidence

- [ ] Version, source revision, dependency lock state, and policy baseline recorded.
- [ ] Model and prompt versions recorded, or provider is explicitly disabled.
- [ ] Backend unit and integration tests pass: `PYTHONPATH=backend python -m pytest backend/tests -q`.
- [ ] Backend compilation passes: `PYTHONPATH=backend python -m compileall -q backend/app backend/tests`.
- [ ] Frontend build passes: `cd frontend && npm ci && npm run build`.
- [ ] Security checks cover path containment, bounded uploads, safe errors, redacted diagnostics, and replay/stale-action behavior.
- [ ] Accessibility smoke review covers keyboard navigation, focus visibility, headings, labels, reduced motion, and non-color status cues.
- [ ] AI evaluation is run with a deterministic provider substitute; skipped live-provider tests are recorded as skipped, not passed.
- [ ] Clean-install and upgrade checks are completed on the supported Windows baseline.
- [ ] Backup and restore validation includes hashes, database state, metadata history, and representative package verification.
- [ ] No critical defects or secret-bearing artifacts remain.

## Release evidence

Record the following with the release artifact:

- Application version and source revision
- Dependency lockfile checksums
- Policy version and verification status
- Provider/model/prompt versions or provider-disabled status
- Test results and intentionally skipped gates
- Known issues, owners, and due dates
- Rollback and data-preservation instructions

A skipped gate must include a reason, owner, and due date. It must never be represented as a pass.
