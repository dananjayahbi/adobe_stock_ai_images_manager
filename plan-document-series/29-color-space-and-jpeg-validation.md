# 29 — Color Space and JPEG Validation

## Purpose
Define deterministic checks for color representation, ICC profiles, channels, JPEG structure, and file size before an image can enter ready staging.

## Scope
The plan covers RGB/RGBA and related modes, profile identification, sRGB normalization, baseline JPEG properties, quality observations, and the maximum file size. It does not define general image conversion or IPTC/XMP injection.

## Decisions / requirements
The evaluated artifact must be identified by hash and role. The validator reads actual decoded channels and file markers rather than trusting extension or MIME type. The canonical ready output is a valid baseline RGB JPEG in sRGB, subject to current policy verification. Grayscale, indexed, CMYK, malformed, or unsupported profiles receive explicit conversion, warning, or failure outcomes according to configured policy; they are never silently labeled sRGB.

RGBA and transparency require a separate decision. If flattening is permitted, the background rule, color management, and visual consequence are recorded, and the output is revalidated. If it is not permitted, the item remains review-required or fails before packaging. Embedded ICC profile identity, conversion tool version, and output profile status are evidence fields.

JPEG validation checks that the file decodes, has expected dimensions, uses supported baseline structure, contains no truncated data, and stays at or below the configured maximum, initially 45 MB. File size is measured on the exact artifact intended for export. Quality values are not inferred as a universal visual-quality score; excessive compression may generate a warning based on calibrated evidence. Re-encoding is limited to one authoritative normalized derivative to avoid cumulative loss.

The validator reports separate findings for format, channels, profile, size, and decode integrity. A pass from one finding cannot hide another. Read-back after normalization and after metadata embedding confirms pixels, dimensions, profile, and file structure remain acceptable.

## Affected blueprint areas
This refines the baseline RGB JPEG requirement, sRGB conversion stage, 45 MB limit, normalization service, ExifTool packaging, and ready-pool validation.

## Dependencies
It depends on safe file validation, normalization, current Adobe policy, QC aggregation, ICC/profile support, and metadata read-back verification.

## Acceptance criteria
- Actual format and channels are validated independently of extension.
- sRGB status is evidenced, not assumed.
- Transparency and unsupported profiles have explicit outcomes.
- Maximum size is checked on the final export artifact.
- Metadata embedding cannot silently alter pixels or invalidate JPEG structure.
- Boundary and corrupt-file fixtures exist.

## Risks / open questions
ICC conversion differences across libraries may affect color appearance. The canonical JPEG quality and chroma-subsampling settings need calibration. The owner must decide whether grayscale images are acceptable commercially and what default background, if any, is allowed for transparency.