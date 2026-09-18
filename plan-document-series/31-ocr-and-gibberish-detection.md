# 31 — OCR and Gibberish Detection

## Purpose
Define a cautious OCR-based signal for unreadable or distorted text without rejecting legitimate signage, typography, or multilingual content merely because text is present.

## Scope
The plan covers OCR preprocessing, language configuration, extracted evidence, gibberish heuristics, confidence, privacy, review behavior, and failure handling. It does not define semantic trademark analysis or general text metadata validation.

## Decisions / requirements
OCR is a review signal first. Detection must distinguish “text detected,” “text appears readable,” “text appears structurally suspicious,” and “OCR unavailable.” Presence of text is not itself a failure. The configured language set, OCR engine and version, page segmentation mode, preprocessing, image scale, and execution timestamp are recorded so results can be reproduced or explained.

The detector may flag candidate gibberish using bounded, interpretable features such as low-confidence tokens, abnormal character patterns, repeated symbols, implausible word structure, and disagreement across preprocessing variants. These features are evidence, not proof. Legitimate invented names, non-Latin scripts, stylized typography, signage, and decorative marks require manual review rather than automatic rejection unless a current policy rule clearly requires otherwise.

OCR output is privacy-sensitive. Store only bounded snippets or token summaries needed for evidence, redact likely personal data where feasible, and avoid writing full recognized text to ordinary logs. Evidence points to an artifact and, where supported, a bounded region or thumbnail. OCR failures, missing language packs, and timeouts produce NOT_EVALUATED or review-required outcomes, not a false pass.

The result includes detected-text count, confidence summaries, language configuration, suspicious-token reasons, region references, and rule version. Human reviewers must be able to inspect the image and dismiss or confirm the finding with a reason. Confirmed issues should remain distinct from automated suspicion. OCR does not replace semantic review for logos, protected names, or misleading content.

## Affected blueprint areas
This refines the blueprint’s Tesseract scan, pseudo-lettering heuristic, deterministic QC contract, review evidence, privacy logging, and calibration fixtures.

## Dependencies
It depends on safe decoding, language-pack deployment, OCR version pinning, policy severity rules, human review, and test fixtures across scripts and typography.

## Acceptance criteria
- Text presence is not automatically treated as a defect.
- Configuration and engine versions are persisted with results.
- Suspicion is explainable and reviewable with bounded evidence.
- OCR failure never becomes an invisible pass.
- Sensitive recognized text is minimized in storage and logs.
- False-positive and multilingual fixtures are included.

## Risks / open questions
The supported language set is unresolved. OCR quality varies with resolution, font, and stylization. The project must set a threshold for automatic hard blocking, if any, and determine whether region-level redaction is sufficient for privacy obligations.