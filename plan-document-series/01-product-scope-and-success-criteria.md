# 01 — Product Scope and Success Criteria

## Purpose
Define the minimum viable Adobe Stock AI Image Studio: a local, human-supervised workstation that converts batches of generated raster images into technically checked, reviewable, metadata-tagged files ready for manual Adobe Stock submission. This document makes throughput, quality, and safety measurable without promising automatic acceptance.

## Scope
The MVP covers local image intake, deterministic technical checks, optional multimodal review, human inspection, metadata generation, metadata embedding, and staging in a ready-to-upload directory. It includes a Next.js dashboard, FastAPI service, SQLite persistence, local storage, OCR, image processing, Gemini integration, and ExifTool packaging. It excludes direct Adobe Stock API submission, unattended publishing, vector conversion, prompt generation, marketplace analytics, cloud synchronization, mobile clients, and multi-user collaboration.

## Decisions and requirements
The system must preserve the original uploaded asset and make every derived file traceable to it. JPEG eligibility is evaluated against a 4.0 MP minimum, with 12 MP or higher recommended, a 45 MB maximum, sRGB output, and a calibrated sharpness policy. These values are product defaults, not permanent claims about Adobe policy; policy-sensitive values must be configurable and reviewed before release.

Human approval remains mandatory before packaging. AI audit results are advisory evidence, not an automatic publishing authorization. The product should support batches sized for a newer contributor’s practical queue, with 50 files as an initial operational example. Success means a reviewer can understand why an image passed or was flagged, correct or reject it, and find the final file and metadata without manipulating database records or raw paths.

## Affected blueprint areas
This scope governs the blueprint’s executive workflow, Adobe Stock baseline table, FastAPI stages, SQLite image record, QC engine, Gemini services, ExifTool service, ready-to-upload pool, and Next.js dashboard. It also establishes boundaries for later domain, API, UX, testing, and operations documents.

## Dependencies
The product depends on verified Adobe Stock contributor requirements, an installed Python runtime and image-processing stack, Tesseract for OCR, ExifTool, a configured Gemini credential, SQLite, and a supported Node/Next.js environment. Detailed contracts are delegated to documents 03, 07–13, 21–44, and 45–67.

## Acceptance criteria
- MVP boundaries and non-goals are approved and referenced by later plans.
- A complete local path exists from upload through human approval to ready staging.
- Original files cannot be silently overwritten by normalization or metadata operations.
- Every candidate exposes technical results, semantic findings, metadata, and current status.
- The workflow can handle a representative batch without requiring direct filesystem or database edits.
- Policy-dependent thresholds and disclosure decisions are visibly identified for verification.

## Risks and open questions
The blueprint describes a strong workflow but not a complete product requirement. Adobe requirements may change, and “near-100% acceptance” is not a controllable promise. The exact throughput target, supported operating-system packaging, and whether a reviewer may override a technical warning remain product-owner decisions. Gemini cost, latency, and availability may make full-batch semantic review impractical. The MVP must therefore define graceful degraded operation and record unresolved policy decisions rather than hiding them.