# 32 — Deterministic QC Test Fixtures

## Purpose
Create a controlled fixture strategy that verifies technical QC behavior, protects against detector regressions, and makes threshold changes reviewable.

## Scope
Fixtures cover resolution, color, JPEG structure, transparency, orientation, sharpness, OCR, corruption, unusual dimensions, and boundary values. The plan includes labeling, provenance, expected results, privacy, and execution rules. It excludes multimodal AI evaluation datasets.

## Decisions / requirements
Every fixture has a stable identifier, purpose, source provenance, license or creation record, content hash, expected dimensions and format, policy version, detector expectations, and privacy classification. Synthetic fixtures are preferred for exact boundaries: dimensions exactly at and around 4.0 MP, file sizes near the configured maximum, known profiles, alpha channels, orientation values, and controlled blur levels. Realistic examples are added for texture, smooth scenes, typography, and compression because synthetic images do not capture all detector behavior.

Expected outcomes are expressed per rule, not only as one overall pass. A fixture can expect a warning, hard failure, review-required, or not-evaluated result. Tolerances are explicit for floating-point measures such as Laplacian variance. OCR fixtures record language and engine expectations without requiring exact full-text equality when recognition is inherently variable. Corrupt and hostile files must verify safe rejection and bounded resource use.

The fixture catalog is versioned separately from policy results. A threshold change may require updating expected outcomes, but the prior catalog and test report remain available for comparison. Tests run with pinned library versions and controlled locale, color profiles, OCR language packs, and timezone. Any environment-dependent result is marked and investigated rather than silently accepted.

Fixtures must not contain unlicensed stock imagery, personal information, real trademarks, or unnecessary sensitive text. Generated examples should be reproducible from documented parameters, while binary artifacts remain content-addressed. Test runs report fixture IDs, detector versions, policy version, observed values, and deviations. A failed fixture blocks release when it covers a safety invariant or changes an approved policy boundary.

## Affected blueprint areas
This supports the deterministic QC engine, threshold calibration, image normalization, file validation, OCR, storage safety, release testing, and operations diagnostics.

## Dependencies
It depends on documents 22–31, pinned library versions, current policy decisions, and test-run reporting. Integration tests must also exercise filesystem atomicity and database evidence links.

## Acceptance criteria
- Each detector has boundary, nominal, negative, and failure fixtures.
- Fixtures are legally usable, privacy-reviewed, hashed, and reproducible.
- Expected outcomes are rule-specific and policy-versioned.
- Numeric tolerances and environment controls are documented.
- Corrupt and oversized inputs prove safe bounded behavior.
- Regression reports identify detector or policy drift.

## Risks / open questions
The project still needs an approved fixture owner, storage location, and licensing checklist. OCR and color results may vary across Windows installations. The team must decide the minimum real-image sample size, CI execution time budget, and process for approving changed expectations.