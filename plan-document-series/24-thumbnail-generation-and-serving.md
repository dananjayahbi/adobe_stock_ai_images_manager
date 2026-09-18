# 24 — Thumbnail Generation and Serving

## Purpose
Provide safe, consistent, performant previews for review without confusing thumbnails with authoritative source or export files.

## Scope
The plan covers thumbnail dimensions, aspect handling, naming, generation, caching, lookup, invalidation, and local serving controls. It excludes full-resolution inspection rendering and image normalization policy.

## Decisions / requirements
Thumbnails are derived artifacts tied to a specific source or normalized hash and a named rendition profile. Profiles define maximum dimensions, fit behavior, quality, color handling, and whether orientation is applied. The system must preserve aspect ratio and avoid upscaling small images. A thumbnail may be generated from the normalized candidate for review, but the UI must expose its provenance.

Internal filenames use asset and content identifiers, not user names or paths. Generation writes to a temporary file, validates decodeability and dimensions, then atomically publishes the derivative. Repeating generation for the same input hash and profile returns the existing verified thumbnail. If the source or profile changes, the cache key changes and stale thumbnails are invalidated or retained as historical derivatives.

Serving requires an asset authorization check, safe relative lookup, bounded range behavior, and a content type derived from the registered artifact rather than request text. The endpoint must not permit arbitrary filesystem reads, path traversal, directory listing, or access to originals unless a separate protected inspection route authorizes it. Cache headers may be used locally, but a changed hash must result in a new URL or validator so browsers do not show stale evidence.

Large batches should not generate every size synchronously during upload. Thumbnail jobs are bounded and can be retried independently. A missing thumbnail is a recoverable presentation issue, not evidence that the asset passed QC. The UI should display a clear unavailable state and allow regeneration without changing asset decisions.

## Affected blueprint areas
This refines the thumbnail storage directory, Next.js image grid and inspection modal, FastAPI serving routes, background workers, and filesystem cleanup.

## Dependencies
It depends on file validation, normalization, durable jobs, storage roles, API access control, and retention policy. Frontend performance requirements belong to document 57.

## Acceptance criteria
- Thumbnails preserve aspect ratio and have bounded dimensions.
- Every thumbnail is traceable to an input hash and rendition profile.
- Serving cannot escape configured storage roots.
- Cache invalidation prevents stale evidence after source changes.
- Missing or failed thumbnails do not alter QC or approval state.
- Regeneration is safe, idempotent, and independently observable.

## Risks / open questions
The project must choose preview profiles and maximum pixel sizes for high-resolution batches. Local browser caching may retain rejected images longer than desired. Whether originals can be served for 100% inspection through the same route requires a separate security decision.