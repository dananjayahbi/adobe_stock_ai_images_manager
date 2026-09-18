# 28 — Resolution and Megapixel Validation

## Purpose
Specify deterministic resolution checks that identify files below minimum eligibility, provide useful recommendations, and avoid misleading conclusions for unusual dimensions or oversized images.

## Scope
The check covers decoded width and height, pixel count, aspect ratio, configured minimum and target values, orientation handling, and related file-size observations. It does not define color, sharpness, or JPEG encoding checks.

## Decisions / requirements
Megapixels are calculated from decoded pixel dimensions, not filename claims or compressed byte size. The canonical value is width multiplied by height divided by one million, rounded only for display; comparisons use full precision. Width and height are recorded before and after orientation normalization when orientation changes how a reviewer perceives the image. The source and evaluated derivative are both identified.

The starting hard minimum is 4.0 MP, with a configurable recommended target derived from the policy baseline. Recommendation is a warning or informational signal and must not be mislabeled as a hard Adobe requirement. The 45 MB file-size limit is reported by a separate file-size rule, while this check can expose unusual compression or dimension relationships for review.

Extremely small dimensions, zero or invalid dimensions, decoder disagreement, and impossible aspect ratios are validation failures. Very wide or tall images are not rejected solely because they are unusual; they receive a configurable review signal unless current policy defines an applicable limit. A portrait or landscape orientation must not be penalized for metadata orientation alone. Upscaling is not assumed to improve commercial quality, so a normalized image that merely enlarges pixels remains traceable and may receive a warning.

Findings contain observed width, height, exact megapixels, aspect ratio, evaluated hash, threshold version, and safe explanation. Boundary cases at exactly 4.0 MP, just below, and just above must be represented in fixtures. Historical results remain tied to the policy version that produced them.

## Affected blueprint areas
This refines the blueprint’s megapixel gate, target range, image record fields, QC engine, upload validation, review evidence, and acceptance policy.

## Dependencies
It depends on safe decoding, orientation normalization, policy versioning, typed QC results, and test fixtures. File-size and JPEG checks remain separate but may aggregate into one technical audit.

## Acceptance criteria
- Pixel count is calculated from decoded dimensions accurately.
- Exact-boundary behavior is documented and tested.
- Minimum, recommendation, and review signals are distinct.
- Orientation metadata does not create false failures.
- Invalid dimensions fail before later processing.
- Evidence identifies input artifact and policy version.

## Risks / open questions
The product owner must resolve the canonical recommended range because the blueprint mentions multiple targets. Current Adobe limits must be reverified before release. Whether extreme aspect ratios should ever be hard failures is undecided, as is policy for upscaled derivatives.