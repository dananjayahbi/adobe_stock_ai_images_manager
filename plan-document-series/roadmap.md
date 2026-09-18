# Adobe Stock AI Image Studio — Agent Implementation Roadmap

This roadmap orders the 67 planning documents into directional implementation waves. Each wave has no more than ten documents. Agents must complete a wave's prerequisites and verification criteria before starting the next wave.

## Operating rules

1. Read the relevant document headers, dependencies, and acceptance criteria before implementation.
2. Implement one complete wave as a batch; do not gate every micro-document independently.
3. Keep code modular and aligned with the blueprint's existing backend/frontend structure.
4. Do not place implementation code snippets in planning documents.
5. Preserve originals and make file, database, AI, and export operations idempotent.
6. A document involving external Adobe Stock policy must record its verification date and source.
7. If a contract is missing, mark the document blocked and record the decision required; do not invent a silent default.
8. Run the wave gate after all documents in the wave are implemented, then record results before proceeding.

## Wave 1 — Product and policy foundation

**Documents:** 01, 02, 03, 04, 05, 06  
**Goal:** Establish scope, user journeys, policy assumptions, human review boundaries, and acceptance thresholds.  
**Gate:** Product owner accepts MVP boundaries; policy sources and unresolved risks are recorded; every later domain has a defined upstream contract.

## Wave 2 — Architecture, runtime, and operational boundaries

**Documents:** 07, 08, 09, 10, 11, 12, 13  
**Goal:** Fix system boundaries, versions, deployment model, configuration, storage lifecycle, error taxonomy, and diagnostics.  
**Gate:** A clean architecture decision record exists for local deployment, storage, configuration, errors, logging, health checks, and external-tool prerequisites.

## Wave 3 — Domain model and persistence

**Documents:** 14, 15, 16, 17, 18, 19, 20  
**Goal:** Define entities, image records, status transitions, database schema, migration policy, deduplication, and recovery.  
**Gate:** Every state and persistence relationship has an invariant; migration and restore procedures cover both database and filesystem data.

## Wave 4 — Secure ingestion and processing infrastructure

**Documents:** 21, 22, 23, 24, 25, 26  
**Goal:** Define safe uploads, normalization, thumbnails, worker dispatch, atomic filesystem changes, and cleanup.  
**Gate:** The upload-to-job contract handles invalid files, duplicate content, partial failures, cancellation, restart recovery, and path safety.

## Wave 5 — Deterministic quality control

**Documents:** 27, 28, 29, 30, 31, 32  
**Goal:** Turn technical QC into typed, testable contracts covering resolution, color, JPEG validity, sharpness, OCR, and fixture design.  
**Gate:** Thresholds are classified as hard failures or warnings, calibration evidence is defined, and fixtures cover expected false-positive cases.

## Wave 6 — AI provider and semantic decision layer

**Documents:** 33, 34, 35, 36, 37, 38, 39  
**Goal:** Define provider abstraction, semantic audits, metadata generation, output validation, cost controls, provenance, and human re-audit.  
**Gate:** Invalid, unsafe, unavailable, rate-limited, and malformed AI responses have deterministic handling; no AI confidence value alone silently bypasses human policy.

## Wave 7 — Metadata packaging and approval finalization

**Documents:** 40, 41, 42, 43, 44  
**Goal:** Define metadata versions, IPTC/XMP/EXIF mapping, embedding verification, ready-pool packaging, and finalization transitions.  
**Gate:** A finalized asset has verified metadata, collision-safe output, a manifest, reproducible provenance, and an idempotent READY transition.

## Wave 8 — Backend API and concurrency contracts

**Documents:** 45, 46, 47, 48, 49  
**Goal:** Expose stable REST resources, schemas, pagination, session boundaries, security controls, and job progress.  
**Gate:** API contracts cover normal, invalid, concurrent, unauthorized, cancelled, and partially failed operations without leaking filesystem paths or secrets.

## Wave 9 — Frontend review workstation

**Documents:** 50, 51, 52, 53, 54  
**Goal:** Define the operator dashboard, ingestion UX, review evidence, approval and override flows, bulk actions, ready-pool UX, accessibility, responsiveness, and performance.  
**Gate:** A reviewer can process a batch with visible progress, safe decisions, keyboard support, clear errors, and no dead actions; large batches remain usable.

## Wave 10 — Verification, installation, release, and future scope

**Documents:** 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67  
**Goal:** Define automated tests, AI evaluation, E2E, load, security, Windows setup, release gates, operations, and post-MVP boundaries.  
**Gate:** Release criteria are executable, installation is reproducible on the target OS, operational recovery is documented, and deferred capabilities are separated from MVP commitments.

## Cross-wave ownership rules

- Product and policy contracts are owned by Wave 1; implementation waves may not change them silently.
- Persistence and state invariants are owned by Wave 3; API and UI documents consume them.
- File safety and lifecycle are owned by Wave 4; every later file operation must reference them.
- QC and AI output schemas are owned by Waves 5 and 6; frontend documents must not redefine them.
- READY and export semantics are owned by Wave 7.
- API wire contracts are owned by Wave 8.
- UX behavior is owned by Wave 9, while release evidence is owned by Wave 10.

## Status tracking

| Wave | Status | Notes |
|---:|---|---|
| 1 | Implemented | Product/policy contracts and human-supervised lifecycle foundation implemented; external policy verification and product-owner sign-off remain release gates |
| 2 | Implemented | Localhost runtime configuration, managed storage layout, safe error envelope, and local diagnostics implemented; durable jobs, persistence, and native-tool checks remain later-wave work |
| 3 | Implemented | SQLite domain persistence, schema migration guard, lifecycle events, source hashing, deduplication, and verified-export gating implemented |
| 4 | Implemented | Secure image ingestion, content validation, immutable source registration, normalized JPEGs, thumbnails, atomic publication, and durable job claiming implemented |
| 5 | Implemented | Versioned technical QC audits for resolution, color/JPEG structure, sharpness, OCR, bounded aggregation, and regression fixtures implemented |
| 6 | Implemented | Provider-neutral AI contracts, injectable Gemini transport boundary, semantic and metadata validation, bounded retry/budget controls, and secret-free provenance implemented; durable AI audit persistence and full human override/re-audit state integration remain follow-up work |
| 7 | Implemented | Immutable metadata versions, approval provenance, deterministic collision-safe ready packaging, and export manifests implemented; ExifTool read-back embedding remains a follow-up integration boundary |
| 8 | Implemented | Version-neutral API schemas, cursor pagination, idempotency, session expiry, safe response filtering, error envelopes, and job progress snapshots implemented; FastAPI route adapter and durable database-backed session/idempotency records remain follow-up work |
| 9 | Implemented | Vite/React review workstation, queue triage, inspection evidence, provenance, approval gating, provider-degraded state, responsive layout, accessibility cues, and reduced-motion support implemented; API integration and production image viewer remain follow-up work |
| 10 | Implemented | Backend release evidence, bounded support bundles, backup manifests, security tests, CI validation, release checklist, and operations runbook implemented; native Windows installer, full browser E2E, live AI evaluation, and formal load/security lanes remain follow-up work |

## Scope note

The separate mobile-audit roadmap supplied in the request targets a different repository and Flutter codebase. This repository contains the Adobe Stock blueprint and planning-series directory, so its Wave 1 is treated here as the product/policy foundation rather than as a Flutter implementation wave.