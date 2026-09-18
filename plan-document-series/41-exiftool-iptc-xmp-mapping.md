# 41 — ExifTool IPTC and XMP Mapping

## Purpose
Establish one canonical mapping from approved studio metadata to embedded JPEG fields so marketplace drag-and-drop behavior is predictable and conflicting containers do not produce ambiguous values.

## Scope
The mapping covers title, description, keywords, creator and disclosure-related boundaries, character encoding, repeated keyword fields, and preservation of unrelated metadata. It does not define process invocation or read-back verification.

## Decisions / requirements
The approved title maps to IPTC ObjectName and XMP dc:Title as the primary short title fields. The approved descriptive text, if separately supported, maps to IPTC Caption-Abstract and XMP dc:Description; the system must not duplicate a title into a description merely because the blueprint example does so. Ordered keywords map to repeated IPTC Keywords values and XMP dc:Subject values, preserving order where the container supports it. A canonical mapping table and field precedence rule must be maintained.

The system writes only fields authorized by the packaging contract. It must preserve technical EXIF data, color profile information, orientation policy, and unrelated user metadata unless privacy or normalization rules require removal. Creator, copyright, location, and contact fields are not invented from provider output. Generative-AI disclosure is a review checklist and portal action unless current policy explicitly defines a supported embedded field; embedding searchable words such as “AI” is not a substitute.

Encoding uses Unicode-safe ExifTool arguments and an explicit character policy. Empty optional fields are omitted or cleared intentionally according to versioned export rules. Duplicate keywords are prevented before invocation. Field names, container versions, ExifTool version, and mapping version are recorded with the export.

If IPTC and XMP values conflict on read-back, the artifact is not ready. The verifier reports the conflicting fields and prevents silent selection. Mapping changes create a new export version and never rewrite historical manifests.

## Affected blueprint areas
This refines the ExifTool example, title and keyword fields, metadata injection stage, ready directory, and Adobe Stock drag-and-drop assumptions. It informs documents 40, 42–44 and API export schemas.

## Dependencies
It depends on approved metadata versioning, current Adobe guidance, ExifTool documentation, JPEG normalization, privacy policy, and read-back verification. Exact field names must be tested against the installed ExifTool release.

## Acceptance criteria
- A versioned mapping defines every written field and precedence rule.
- Title and ordered keywords appear consistently in approved IPTC and XMP fields.
- Unrelated technical metadata is preserved unless explicitly governed.
- Disclosure is not falsely represented as embedded metadata compliance.
- Unicode, duplicate, empty, and conflicting values have deterministic outcomes.
- Mapping and tool versions are present in export provenance.

## Risks / open questions
Adobe ingestion precedence between IPTC and XMP may change. ExifTool may normalize or rewrite fields differently across versions. The owner must decide whether to preserve all user metadata, which creator fields are user-editable, and whether a separate description is required for MVP.