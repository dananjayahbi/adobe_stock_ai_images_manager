# 23 — Image Normalization Pipeline

## Purpose
Define how accepted source images become stable, policy-compliant derivatives without altering originals or hiding transformations from reviewers.

## Scope
The pipeline covers orientation, color management, alpha handling, JPEG encoding, metadata treatment, quality checks, and provenance. It excludes thumbnail-specific behavior and final IPTC/XMP packaging.

## Decisions / requirements
The original source remains byte-for-byte immutable. Normalization produces a new derivative with a parent reference, input hash, tool and library versions, configuration, and output hash. The pipeline must read EXIF orientation and apply it exactly once, then emit a canonical orientation state. Review evidence must identify whether the displayed image is original or normalized.

The canonical ready candidate is a baseline RGB JPEG in sRGB, subject to current policy. Images with alpha require an explicit background policy; silently flattening transparency against an arbitrary color is not acceptable. The default should be a review-required outcome unless a configured and documented flattening rule is selected. CMYK, grayscale, indexed, Display P3, AdobeRGB, and malformed profiles receive explicit conversion or review outcomes, with the source profile recorded.

Encoding parameters are configurable and bounded by file-size and quality requirements. The pipeline must avoid repeated lossy re-encoding by treating one normalized derivative as authoritative for downstream stages. It must preserve dimensions unless a policy-approved transformation is necessary and must record any resize or crop. Metadata stripping is separate from metadata generation: unsafe or stale embedded fields may be removed, but generated title and keywords are not inserted until approval and packaging.

Normalization is idempotent for the same source hash and configuration. A failed conversion leaves the source intact and produces no claimed ready derivative. Post-write validation reopens the output, verifies dimensions, color mode, profile, JPEG structure, and hash, then registers it atomically.

## Affected blueprint areas
This refines the color-space normalization stage, Pillow/OpenCV processing, inbox and derived storage, reviewer image display, and ExifTool packaging boundary.

## Dependencies
It depends on file validation, deterministic QC contracts, policy versions, filesystem atomicity, and the chosen image libraries. Alpha and color-management decisions must align with Adobe policy verification.

## Acceptance criteria
- Originals are never overwritten or re-encoded in place.
- Orientation is applied once and recorded.
- Output profile and channel state are verifiable.
- Alpha, unsupported profiles, and conversion failures have explicit outcomes.
- Repeating normalization with identical inputs is idempotent.
- Output validation occurs before downstream QC or packaging.

## Risks / open questions
Color conversion quality depends on available ICC profiles and library behavior. Flattening transparent images can change commercial meaning. The owner must choose default JPEG quality, whether to preserve selected non-sensitive metadata, and whether source dimensions may ever be reduced.