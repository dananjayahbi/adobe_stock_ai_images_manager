# 06 — Acceptance Policy and Threshold Calibration

## Purpose
Turn technical and semantic signals into a transparent acceptance policy with calibrated thresholds, severity classes, and evidence requirements. The goal is consistent reviewer guidance, not a false guarantee of marketplace acceptance.

## Scope
The policy covers resolution, file size, color, JPEG validity, sharpness, OCR and gibberish detection, semantic confidence, artifact categories, metadata limits, and approval eligibility. It includes calibration and monitoring expectations but not the implementation of individual detectors.

## Decisions and requirements
Each check must produce a structured result containing a rule identifier, observed value, threshold or rule version, severity, explanation, and evidence reference. Hard failures block approval unless an explicitly documented exception is allowed. Warnings remain visible and require reviewer judgment. Informational signals cannot change state by themselves.

Initial technical policy uses 4.0 MP as a minimum, recommends higher-resolution source material, targets sRGB baseline JPEG, enforces the 45 MB maximum, and begins sharpness calibration around variance 120. These are starting points derived from the blueprint. Thresholds must be tested against representative accepted-looking, rejected-looking, blurred, text-heavy, transparent, compressed, and unusual-aspect images. Semantic confidence around 0.75 may prioritize review, but it must not be treated as universal truth.

Calibration should measure false positives, false negatives, reviewer disagreement, and provider drift. Changes to a threshold require a policy version and regression review. Historical decisions retain the rule version used at the time. A “needs manual verification” outcome is preferable to silently converting uncertainty into pass.

## Affected blueprint areas
This document governs the QC engine’s result contract, technical thresholds, Gemini pass logic, metadata validator, review badges, state machine eligibility, fixtures, AI evaluation, and release gates. It is upstream of documents 27–32, 34–39, 53–55, 60, and 65.

## Dependencies
Calibration requires labeled fixtures and reviewer judgments, current Adobe policy, deterministic detector implementations, AI provider response contracts, and persistent provenance. It also depends on a configuration system that can select policy versions safely.

## Acceptance criteria
- All checks have explicit severity and eligibility behavior.
- Threshold values are traceable to policy or calibration evidence.
- Boundary and false-positive fixtures exist for each detector.
- Confidence scores are displayed as evidence, never as automatic approval.
- Policy changes are versioned and historical results remain interpretable.
- Release testing includes representative end-to-end acceptance scenarios.

## Risks and open questions
Laplacian variance varies with dimensions, subject matter, compression, and preprocessing, so a universal 120 threshold may be misleading. OCR can flag legitimate text or miss distorted lettering. Semantic provider scores are not stable across model versions. The team must select a labeled dataset, define an acceptable error tradeoff, decide whether thresholds vary by asset profile, and identify who owns calibration updates.