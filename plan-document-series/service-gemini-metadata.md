# Service Specification: Gemini Metadata Generator

| Field | Value |
|---|---|
| Document ID | SVC-GEM-META-003 |
| Component | Metadata Generation Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Generate commercially viable titles and keyword sets for verified images using the Gemini 2.5 Flash model. This service produces the IPTC/XMP metadata that will later be embedded into JPEG files by the ExifTool embedder service.

## Responsibilities

| Responsibility | Description |
|---|---|
| Construct Metadata Prompt | Build a prompt specifying exact formatting rules: title must be under 140 characters in natural English, keywords must number between 25 and 35 ordered from most to least important, top 5 keywords must define subject, action, or color. |
| Enforce Forbidden Tags | Include explicit instructions to exclude forbidden terms from both title and keyword output. |
| Prevent Trademark Leakage | Instruct the model to avoid any trademarked terms, brand names, or copyrighted character references. |
| Parse Structured Output | Deserialize the JSON response into a native dictionary containing a title string and a keywords list. |
| Post-process and Sanitize | Apply truncation, capping, and forbidden tag stripping after parsing to guarantee compliance regardless of model adherence. |

## Configuration

| Parameter | Value | Rationale |
|---|---|---|
| Model | Gemini 2.5 Flash | Balances quality of natural language generation with throughput requirements for batch processing. |
| Temperature | 0.2 | Slightly higher than the auditor to allow creative keyword variation while maintaining consistency. |
| Response MIME Type | application/json | Ensures parseable structured output matching the expected schema. |

## Prompt Rules Conveyed to Model

| Rule | Specification |
|---|---|
| Title Length | Under 140 characters |
| Title Language | Natural English, descriptive, commercially appealing |
| Keyword Count | Between 25 and 35 inclusive |
| Keyword Ordering | Most important first, least important last |
| Top 5 Keywords | Must describe subject matter, action depicted, or dominant colors |
| Forbidden Tags | AI, generative, stock, midjourney, illustration, image, nobody, copyspace |
| Trademarks | No brand names, logo references, or copyrighted character names |

## Output Contract

| Key | Type | Description |
|---|---|---|
| title | String | Commercial title under 140 characters describing the image content. |
| keywords | List of Strings | Ordered list of 25 to 35 keywords ranked by relevance. |

## Post-processing Constraints

- If the returned title exceeds 150 characters, truncate it at the nearest word boundary before the 150-character limit. Append an ellipsis only if truncation splits a word.
- Cap the keywords list at exactly 35 entries. Discard any extras beyond position 35.
- Iterate through the returned keywords and strip any that match the forbidden tags list (case-insensitive comparison). This acts as a safety net for model non-compliance.
- If after stripping forbidden tags the keyword count drops below 25, accept the reduced list rather than re-invoking the API. The orchestrator may flag low-count results for manual review.
- Never return raw model output without post-processing. All sanitization steps must execute before the result reaches the orchestrator.
| Field | Value |
|---|---|
| Document ID | SVC-GEM-META-003 |
| Component | Metadata Generation Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |