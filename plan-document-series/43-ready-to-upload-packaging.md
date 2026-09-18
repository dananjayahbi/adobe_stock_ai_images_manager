# 43 — Ready-to-Upload Packaging

## Purpose
Define the final export contract that turns an approved, verified asset into a discoverable and collision-safe ready-to-upload package without implying that the application has submitted it to Adobe Stock.

## Scope
Packaging covers output naming, directory layout, batch grouping, manifests, disclosure checklist visibility, validation gates, collisions, and repeatability. Direct marketplace upload is out of scope.

## Decisions / requirements
Only an item with an attributable human approval, current approved metadata, completed required technical and semantic evidence, verified embedding, and current policy compatibility may enter the ready pool. The source original remains in its lifecycle location; the ready artifact is a derived export linked by content and metadata hashes.

Output names are filesystem-safe, readable, and collision-resistant. Original extensions are not trusted. The naming policy may use a sanitized stem plus stable short identifier, while preserving a manifest mapping output name to source record, source hash, output hash, metadata version, policy version, and export timestamp. User-visible names must not leak full local paths or personal data. A rename or re-export creates a new manifest entry and never silently repoints an old one.

Packages are grouped by user-selected batch or export operation, with an initial operational cap aligned to policy and account constraints. The manifest records item-level success, failure, skipped status, disclosure reminder, and verification evidence. One failed item does not make successful artifacts appear incomplete, but the package summary clearly distinguishes a partial export. The ready directory contains only verified final JPEGs and an intentionally generated manifest; temporary files, logs, and unverified outputs stay elsewhere.

Re-running an export with unchanged source, approved metadata, mapping, tool, and policy versions is idempotent. A changed input or configuration creates a new export identity and invalidates the prior ready status as appropriate. The UI and API provide a checklist reminding the operator to complete Adobe’s generative-AI portal disclosure and any account-specific queue decision.

## Affected blueprint areas
This defines the Stage 5 ready-to-upload pool, storage layout, metadata verification, approval finalization, batch limits, and export UI/API behavior.

## Dependencies
It depends on documents 03, 11, 16, 19, 26, 40–44, and the API and job contracts. Current policy and Windows filesystem constraints must be verified before release.

## Acceptance criteria
- Only fully approved and verified artifacts enter the ready directory.
- Names are safe, collision-resistant, and traceable through a manifest.
- Partial batches report per-item outcomes without hiding failures.
- Repeated identical exports are idempotent.
- Manifests contain source, output, metadata, policy, and verification identities.
- Generative-AI disclosure remains an explicit operator checklist item.

## Risks / open questions
Queue limits vary by contributor account and may not belong in the package validator. Users may move or rename files outside the application, breaking traceability. The owner must decide whether manifests are JSON, CSV, or both, how long ready packages remain registered, and whether archive copies are automatic.