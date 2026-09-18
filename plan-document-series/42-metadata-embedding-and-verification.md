# 42 — Metadata Embedding and Verification

## Purpose
Define a safe, repeatable process for embedding approved metadata and proving that the resulting JPEG remains technically valid, pixel-equivalent, and suitable for ready staging.

## Scope
This document covers temporary outputs, ExifTool invocation, argument safety, exit handling, read-back, pixel and structure checks, atomic replacement, and failure recovery. It does not define the field mapping itself or ready-batch packaging.

## Decisions / requirements
Embedding operates on a staged copy of the normalized export, never on the preserved original or the only copy of a ready artifact. The service creates a unique temporary path in the same filesystem, passes arguments without shell interpolation, applies an explicit ExifTool executable configuration, and captures bounded stdout and stderr. Filenames and metadata values are treated as data, not command fragments.

A successful process exit is necessary but insufficient. The verifier reads back all required IPTC and XMP fields, compares title and ordered keywords with the approved metadata version, checks the mapping version, and confirms no required field is truncated or unexpectedly duplicated. It re-runs JPEG decode, dimensions, RGB/sRGB, baseline structure, file-size, and profile checks against the exact output. A pixel fingerprint or decoded-pixel comparison proves that metadata embedding did not alter image content within the approved tolerance.

The temporary output is atomically moved into its final location only after all verification succeeds. Existing ready artifacts are never overwritten unless the export identity and idempotency rules explicitly permit replacement; otherwise a collision produces a new safe name or a terminal conflict. On any failure, the temporary file is quarantined or deleted according to recovery policy, the source remains available, and the item receives a recoverable packaging failure.

Verification records tool version, command category without secrets, input and output hashes, field results, technical recheck, timestamps, and failure diagnostics. Re-running the same approved version should produce an equivalent result or an explicit tool-version difference.

## Affected blueprint areas
This hardens `exif_service.py`, Stage 4 metadata injection, the JPEG validation stage, filesystem atomicity, ready staging, and operational diagnostics.

## Dependencies
It depends on documents 22–26, 29, 40–41, 43–44, ExifTool installation, and content-hash conventions. Windows process and path behavior must be covered by the deployment plan.

## Acceptance criteria
- Originals are never modified by embedding.
- ExifTool arguments are safe for arbitrary filenames and metadata.
- Read-back verifies every required mapped value and ordering rule.
- Final JPEG technical checks pass after embedding.
- Pixel content and dimensions remain unchanged within policy tolerance.
- Failed temporary operations cannot appear in the ready pool.

## Risks / open questions
ExifTool may rewrite metadata or profiles in ways that vary by version. Pixel comparison can be expensive for large images. The team must choose the exact fingerprint method, temporary-file retention policy, and behavior when optional user metadata cannot be preserved.