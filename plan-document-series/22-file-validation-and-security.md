# 22 — File Validation and Security

## Purpose
Prevent malformed, deceptive, oversized, or unsafe inputs from entering image processing or external-provider flows.

## Scope
The plan covers filename and path handling, byte limits, image identity, decoder validation, decompression risks, metadata handling, and quarantine outcomes. It does not define deterministic QC thresholds or normalization output policy.

## Decisions / requirements
User-supplied names are never used as paths. The service strips directory components, rejects traversal and control characters, applies a bounded display-name policy, and generates internal names from stable identifiers. All storage paths are resolved beneath configured roots and checked against those roots before access. Symlinks, junctions, and unexpected reparse points must be rejected or handled according to a documented Windows policy.

Content type and extension are hints only. The validator must inspect magic bytes, decode the image with a bounded library, verify dimensions and channel structure, and reject files whose decoded identity conflicts with the declared format. Corrupt, truncated, multi-frame, animated, or unsupported inputs receive explicit outcomes. A file must be rejected before OCR, semantic upload, or metadata embedding if it cannot be safely decoded.

Resource limits apply to compressed bytes, decompressed dimensions, pixel count, memory pressure, processing time, and nested or unusual metadata. The application must protect against decompression bombs and parser hangs through library limits, isolated processes where needed, and timeouts. Metadata is treated as untrusted input; it is read only through safe libraries and stripped or normalized according to document 23.

Validation results include rule identifiers, observed facts, severity, safe user-facing explanation, and quarantine or cleanup instructions. Suspicious inputs are retained in a restricted quarantine area for diagnosis, not copied into active processing directories. Logs record hashes and bounded diagnostics without embedding sensitive payloads. Provider calls are allowed only after local validation and policy checks pass.

## Affected blueprint areas
This hardens the upload endpoint, inbox, Pillow/OpenCV/OCR pipeline, Gemini boundary, ExifTool wrapper, configuration limits, and local filesystem access.

## Dependencies
It depends on upload limits, storage roots, Windows deployment assumptions, normalization rules, error taxonomy, and security testing. External library versions must be pinned and reviewed.

## Acceptance criteria
- Traversal, absolute paths, symlinks, and unsafe names are handled safely.
- Format identity is verified independently of extension and header claims.
- Oversized or hostile images cannot cause unbounded memory or CPU use.
- Invalid files are quarantined or removed without damaging valid assets.
- Validation occurs before OCR, AI submission, or packaging.
- Security events are diagnosable without leaking image contents or secrets.

## Risks / open questions
The supported format set is expected to be JPEG-focused, but the accepted intake formats need a product decision. Windows antivirus and file locks can produce transient validation failures. The team must choose process isolation boundaries and define whether suspicious files remain available for forensic review.