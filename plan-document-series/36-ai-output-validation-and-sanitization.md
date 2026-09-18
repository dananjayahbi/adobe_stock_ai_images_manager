# 36 — AI Output Validation and Sanitization

## Purpose
Ensure that all provider output is treated as untrusted input and converted into safe, bounded domain data before it affects review, metadata, persistence, or packaging.

## Scope
This document covers parsing, schema validation, bounds, normalization, duplicate handling, prohibited terms, malformed output, and rejection behavior for semantic and metadata responses. It does not define provider retries, prompt wording, or ExifTool mapping.

## Decisions / requirements
Validation occurs immediately after provider transport and before database fields or state transitions are updated. The system accepts only the documented structured response shape. Markdown fences, commentary, multiple JSON objects, invalid encoding, unexpected scalar types, and truncated output are invalid unless a narrowly defined parser recovery rule is applied and recorded. Recovery must never guess a missing safety field.

Semantic output validation bounds all confidence values to the inclusive 0.0–1.0 range, rejects NaN and infinity, requires recognized finding categories, limits collection length and explanation size, and normalizes whitespace. Unknown categories become an explicit unknown finding or invalid response according to policy; they must not disappear silently. A missing recommendation, contradictory pass with blocking finding, or absent confidence produces review-required status.

Metadata validation enforces the approved title length by characters, rejects empty or control-heavy titles, normalizes Unicode to the selected form, trims whitespace, and preserves meaningful punctuation. Keywords are trimmed, normalized, bounded by count and length, deduplicated case-insensitively while preserving first occurrence order, and checked against prohibited terms and trademark-risk dictionaries. The validator records removed or changed values without exposing secrets. It must not invent replacement keywords; insufficient output requires regeneration or manual editing.

Sanitization is deterministic and policy-versioned. It may remove provider formatting artifacts, but it cannot rewrite content to conceal a legal or semantic concern. Every rejected response retains a bounded diagnostic, provider provenance, and a retry classification. Validated output is still advisory until a reviewer approves it and finalization verifies it.

## Affected blueprint areas
This adds the missing trust boundary between `gemini_service.py`, image records, semantic confidence, title and keyword fields, review states, and ExifTool packaging. It directly supports documents 34, 35, 37–40, and 44.

## Dependencies
It depends on documents 03, 12, 33–35, 38, 40, and the shared schema and error conventions. Prohibited-term sources and Unicode policy require product and legal approval.

## Acceptance criteria
- No unvalidated provider value changes eligibility or metadata state.
- Bounds and collection limits prevent resource abuse.
- Invalid JSON and contradictory results become explicit failures or review-required outcomes.
- Keyword normalization preserves approved order and records transformations.
- Prohibited terms are detected consistently in titles and keywords.
- Validation is deterministic, tested, and versioned.

## Risks / open questions
Over-aggressive normalization may damage legitimate names or non-English text. Trademark dictionaries can be incomplete and create false confidence. The team must decide whether unknown semantic categories are retained as review findings or cause full response rejection, and how manual edits interact with later revalidation.