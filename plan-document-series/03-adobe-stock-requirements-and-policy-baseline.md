# 03 — Adobe Stock Requirements and Policy Baseline

## Purpose
Create a verified, versioned policy baseline for technical eligibility, metadata, generative-AI disclosure, and practical submission limits. The application must separate externally sourced policy from internal heuristics and make policy changes manageable.

## Scope
The baseline covers JPEG format, dimensions and megapixels, file size, color space, image quality, text and artifact review, titles, keywords, generative-AI labeling, and contributor queue considerations. It does not define legal advice, guarantee acceptance, or automate submission to Adobe Stock. External requirements must be rechecked at release and whenever Adobe changes contributor guidance.

## Decisions and requirements
The blueprint provides initial operating assumptions: baseline RGB JPEG, at least 4.0 MP, a recommended 12–25 MP range, a 45 MB maximum, sRGB, and a Laplacian variance starting threshold of 120. The system should expose these as versioned configuration, not hard-code them across services. A threshold must be labeled as hard gate, warning, or review signal, with rationale and calibration evidence.

Titles should be natural, descriptive, and under the product’s chosen character limit; the blueprint references both 140 and 150 characters, so one canonical limit must be selected before implementation. Keywords should be relevant, ordered by importance, and capped below the marketplace maximum; the initial generation target is 25–35. Forbidden or risky terms must be validated locally after generation. “AI” and generative terminology may be required in a portal disclosure even when excluded from searchable keywords; this distinction must be explicit.

Every release must record source URLs or documents, access date, policy interpretation, and the product version that adopted it. When policy is uncertain, the UI should label the item for manual verification instead of silently accepting it.

## Affected blueprint areas
This plan governs the commercial and technical baseline table, QC thresholds, Gemini metadata prompt rules, ExifTool fields, ready-pool workflow, and dashboard disclosure cues. It is upstream of documents 04–06, 27–44, and 65.

## Dependencies
Accurate implementation requires current Adobe Stock contributor documentation, internal legal review, calibrated image fixtures, and decisions about title length, keyword count, language, and batch sizing. It also depends on configuration and provenance plans so policy versions accompany audit results.

## Acceptance criteria
- Each policy rule has a source, verification date, owner, and product interpretation.
- Technical thresholds are configurable and classified by enforcement severity.
- Metadata limits and forbidden terms are consistent across generation, validation, UI, and packaging.
- Generative-AI disclosure is represented separately from searchable metadata.
- A policy update can be applied without rewriting historical audit evidence.
- No document promises acceptance or treats current policy as permanent.

## Risks and open questions
The source blueprint contains an internal inconsistency between 140- and 150-character title limits and between minimum and recommended megapixel language. Adobe may change limits, keyword practices, or disclosure requirements. Queue limits are account-dependent and should not be presented as a universal rule. A policy owner must resolve canonical values and decide how stale metadata is identified when requirements change after an asset was packaged.