# Adobe Stock AI Image Studio backend

Wave 1 establishes product and policy contracts before implementing persistence, ingestion, QC, AI, or API layers.

Wave 2 adds validated localhost configuration, managed storage directories, safe error envelopes, and local health diagnostics.

Wave 3 adds SQLite persistence for batches, assets, files, jobs, state events, and exports, with source-hash deduplication and verified-export gating.

Wave 4 adds secure ingestion, decoder-backed validation, immutable source preservation, idempotent normalization and thumbnails, and durable job claims.

Wave 5 adds deterministic technical QC for resolution, color/JPEG structure, Laplacian sharpness, and OCR with explicit non-pass outcomes.

Wave 6 adds a provider-neutral AI boundary with injectable Gemini transport, typed semantic-audit and metadata contracts, deterministic output sanitization, bounded retries and call budgets, and secret-free provenance keys. AI output remains advisory and cannot independently authorize approval or READY.

Wave 7 adds immutable metadata versions, explicit approval provenance, verified collision-safe ready packaging, deterministic export identities, and manifests with source, metadata, policy, and output hashes. Packaging includes a generative-AI disclosure reminder and never modifies preserved originals.

Wave 8 adds framework-neutral local API contracts for bounded cursor pagination, safe error envelopes, optimistic action validation, idempotency replay, expiring operator sessions, redacted asset responses, and durable-job progress snapshots. These contracts are ready for a FastAPI route adapter; no HTTP server is enabled yet.

Wave 9 adds a Vite/React review workstation in `frontend/` with queue-first navigation, triage filters, inspectable evidence, provenance, provider-degraded messaging, approval gates, keyboard-friendly controls, responsive layout, reduced-motion support, and an empty-state path. The current UI uses representative local data until the Wave 8 HTTP adapter is connected.

Wave 10 adds release validation and operational safeguards: backend release metadata and gate tracking, hash-based backup manifests, bounded redacted support bundles, focused security tests, a GitHub Actions CI workflow, a release checklist, and a local operations runbook.

## Wave 1 contracts

- `app.core.policy.PolicyBaseline` stores versioned, configurable policy assumptions.
- `app.core.policy.validate_metadata` enforces the canonical initial title and keyword rules.
- `app.core.workflow.AssetStatus` and `transition` enforce the human-in-the-loop lifecycle.
- `READY` is reachable only from `APPROVED`, with an attributable actor.

The current policy baseline is intentionally marked unverified. Adobe Stock requirements must be verified against current official contributor documentation before release; this repository does not claim marketplace acceptance.

## Wave 2 contracts

- `app.core.config.Settings` validates bounded runtime settings and redacts secrets from diagnostics.
- `app.core.storage.StorageLayout` owns originals, derivatives, quarantine, temporary files, manifests, and diagnostics under one root.
- `app.core.errors.StudioError` provides stable categories and safe user-facing envelopes.
- `app.core.diagnostics` separates liveness, storage, disk, and optional-provider health.

## Wave 3 contracts

- `app.persistence.Database` owns the versioned SQLite schema and conservative migration guard.
- Source bytes are identified with SHA-256 hashes; repeated content returns the existing asset.
- Lifecycle events are append-only records with actor, reason, and UTC timestamp.
- `READY` requires both human approval and a verified export record.

## Wave 4 contracts

- `app.ingestion.IngestionService` validates files before active processing and stores sources beneath managed roots.
- User filenames are display metadata only; internal source names use opaque asset identifiers.
- Normalization and thumbnails write temporary artifacts, validate them, then publish derived files without modifying originals.
- SQLite jobs are claimed transactionally so a queued stage is not processed by two workers at once.

## Wave 5 contracts

- `app.qc.run_technical_qc` returns an immutable, policy-versioned audit with rule-level findings.
- Resolution uses decoded dimensions and a 4.0 MP provisional hard minimum.
- Non-RGB/transparency and unavailable OCR remain explicit review or not-evaluated outcomes.
- Sharpness uses a recorded Laplacian variance signal; the 120 threshold remains provisional and warning-oriented.
- QC input hashes and detector versions are retained in the audit result for reproducibility.

## Wave 6 contracts

- `app.ai.ProviderRequest` captures operation, artifact hash, model, prompt/schema/policy versions, and redacted generation configuration.
- `app.ai.GeminiProvider` is an injectable transport adapter; missing credentials and provider failures are explicit, categorized outcomes.
- `semantic_audit_from_provider` validates bounded findings, confidence values, categories, severity, and contradictory recommendations.
- `metadata_from_provider` normalizes Unicode, deduplicates keywords in order, removes prohibited workflow terms, and enforces the current policy limits without inventing replacements.
- `execute_with_retry` retries only explicitly transient `AiProviderError` instances under a bounded attempt and call budget.
- Provenance keys are deterministic and contain no credentials or raw image bytes; re-audits must create new request contexts.

## Wave 7 contracts

- `app.metadata.MetadataStore` stores append-only metadata versions and distinguishes provider-generated, user-edited, approved, and superseded values.
- Metadata approval requires valid policy checks, an attributable actor, and a reason; edits create successor versions rather than mutating history.
- `app.packaging.package_ready` requires verified artifacts, approval identity, and disclosure acknowledgment before writing a ready JPEG.
- Export identities are deterministic for unchanged source, approved metadata, policy, and artifact inputs; repeated exports reuse the existing manifest.
- Ready manifests include source hash, output hash, approved metadata identity, policy identity, and an explicit portal disclosure reminder.

## Wave 8 contracts

- `app.api.CursorPage` and `paginate` provide deterministic, bounded cursor pagination.
- `validate_action` requires an expected revision, attributable actor, and idempotency key for mutating actions.
- `IdempotencyStore` replays the original result and rejects payload reuse with conflicting input.
- `SessionManager` creates expiring local operator sessions without exposing credentials.
- `safe_asset_response` allow-lists wire fields and bounds evidence; absolute paths and secrets are omitted.
- `JobSnapshot` exposes stage, counters, terminal error summaries, and no worker internals.

## Wave 9 contracts

- The primary workspace is a review queue with Overview-style counts, Review queue, Batches, Ready to upload, Diagnostics, and Settings navigation.
- Queue cards expose lifecycle status, risk, concise issue reason, and a safe next action rather than color alone.
- The inspection panel separates preview, evidence summary, provenance, and approval controls; blocked items cannot be approved.
- Provider-offline state is visible while deterministic QC and manual review remain available.
- Responsive CSS collapses navigation at narrower desktop widths and honors `prefers-reduced-motion`.
- Frontend build validation is provided by `npm run build` in `frontend/`.

## Wave 10 contracts

- `app.release.validate_release_metadata` requires semantic version and policy/model/prompt provenance.
- `ReleaseChecklist` records passed gates and requires reason, owner, and due date for skipped or failed gates; skipped validation is never a pass.
- `create_backup_manifest` copies selected files and records SHA-256 hashes without including secrets.
- `build_support_bundle` emits bounded health and event summaries while excluding credentials, raw prompts, private paths, and uncontrolled payloads.
- `.github/workflows/ci.yml` runs backend tests/compilation and the frontend production build.
- `RELEASE_CHECKLIST.md` and `OPERATIONS_RUNBOOK.md` define release evidence, degraded modes, recovery, backup, and support procedures.

## Test command

Run from the repository root with the backend on `PYTHONPATH`:

```text
$env:PYTHONPATH = "backend"
python -m pytest backend/tests -q
```
