# 30 — Sharpness and Laplacian Calibration

## Purpose
Make the Laplacian-variance sharpness signal reproducible, interpretable, and safe from becoming a universal substitute for visual inspection.

## Scope
The plan covers image selection, grayscale conversion, scaling, Laplacian measurement, thresholds, warnings, exceptions, evidence, and calibration. It does not define semantic artifact review or OCR.

## Decisions / requirements
The detector operates on a registered artifact and records its exact dimensions, color-to-luminance conversion, scaling method, blur or denoise state, OpenCV and detector versions, and measured variance. A consistent evaluation scale is required because variance changes with image dimensions and resampling. If the image is resized for measurement, the scale and interpolation method are fixed by policy and recorded.

The blueprint’s variance value of 120 is an initial calibration point, not a guaranteed universal threshold. The result should support hard failure only when evidence and policy justify it; otherwise low values produce a warning or review-required signal. A detector score cannot override obvious visual defects or guarantee acceptable 100% inspection quality. Highly textured images, smooth studio scenes, illustrations, and intentional depth-of-field require calibration cohorts rather than one undifferentiated threshold.

The output includes the numeric score, threshold, severity, cohort or profile if applicable, and a link to the evaluated artifact. Boundary and repeated-run tests must establish tolerance. If a score is invalid because decoding, scaling, or numerical processing failed, the result is NOT_EVALUATED and blocks automated eligibility until resolved.

Calibration uses labeled examples from accepted-looking sharp images, genuinely blurred images, compressed images, smooth subjects, high-frequency textures, and different resolutions. It measures false positives, false negatives, reviewer disagreement, and score stability after normalization. Threshold changes require a policy version, fixture update, and regression review. Reviewer UI presents the score as evidence with a visual inspection reminder.

## Affected blueprint areas
This refines the Laplacian variance heuristic, acceptance policy, QC evidence, review modal, calibration workflow, and deterministic test fixtures.

## Dependencies
It depends on normalization choice, OpenCV version, policy configuration, labeled fixtures, and human-review criteria. Results aggregate through document 27.

## Acceptance criteria
- Measurement preprocessing is fixed and recorded.
- Same input and configuration produce stable results within tolerance.
- Threshold 120 is treated as provisional until calibrated.
- Smooth and textured image cohorts are evaluated separately.
- Invalid measurement is not treated as pass.
- UI and audit records explain the signal’s limitations.

## Risks / open questions
A single threshold may unfairly reject commercially valid smooth images or miss localized blur. The team must choose whether to use profile-specific thresholds, a hard floor, or warning-only behavior. Calibration labels and acceptable error rates are not yet approved.