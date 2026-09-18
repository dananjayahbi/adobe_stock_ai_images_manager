# 35 — Metadata Generation Prompt and Response Contract

## Purpose
Define the contract for generating truthful, commercially useful titles and keywords while keeping policy-sensitive limits, language, ordering, and disclosure separate from provider-specific prompt text.

## Scope
The contract covers title semantics, keyword quantity and order, language, prohibited terms, subject grounding, response fields, and versioning. It excludes post-generation sanitization, embedding, and approval decisions, which are specified in documents 36, 40–44.

## Decisions / requirements
Metadata generation receives the normalized image plus permitted contextual facts, such as orientation or user-provided subject notes. It must describe visible content rather than infer unsupported biography, location, event, brand, or protected identity. The initial language is English, pending product-owner confirmation. The title is a natural descriptive phrase or sentence and must use the canonical character limit selected from the policy baseline; the existing conflict between 140 and 150 characters must be resolved before implementation.

The initial keyword target is 25–35 relevant terms ordered from most important to least important. Keywords must cover the direct subject, action or use, setting, visual attributes, and legitimate concepts visible in the image. They must not contain spam, repeated variants, unsupported claims, marketplace terms, provider names, generation terminology, or trademarked terms. Searchable keywords are separate from the generative-AI disclosure checklist and must not be used to represent that disclosure.

The structured response contains one title, an ordered keyword list, the requested language, and an optional concise generation note that is not exported as marketplace metadata. The provider must not return multiple alternatives unless the contract explicitly models candidates. Empty or uncertain output is invalid for finalization but may be retained as a failed generation attempt. The prompt instructs the model to avoid the words identified by the policy baseline, while local validation remains authoritative.

Generated metadata is a proposal. Human reviewers can edit it, and the system stores generated, edited, and approved versions separately. The contract records prompt version, model, source hash, policy version, and generation timestamp. A changed image or policy invalidates a previously approved metadata version for ready staging.

## Affected blueprint areas
This refines `METADATA_GENERATION_PROMPT`, the title and keyword fields on `ImageRecord`, the approval endpoint, and the metadata packaging stage. It informs documents 36, 38, 40, 43, 44, and the review UX documents.

## Dependencies
It depends on documents 03–06, 10, 33, 36, 38, and 40. Canonical title length, keyword cap, supported language, and forbidden-term policy must be approved before implementation.

## Acceptance criteria
- Titles and keywords are returned in a typed, versioned shape.
- Ordering and quantity rules are explicit and locally enforceable.
- Generated content is grounded in visible image evidence and contains no silent claims.
- Search metadata is distinct from generative-AI disclosure.
- Generated and approved versions remain separately auditable.
- Policy or source changes invalidate stale metadata for finalization.

## Risks / open questions
The provider may produce plausible but inaccurate concepts, repetitive keywords, or accidental trademarks. Multilingual support could alter tokenization and policy rules. The owner must resolve the title limit, keyword maximum, language roadmap, and whether user notes may influence metadata without becoming unverified claims.