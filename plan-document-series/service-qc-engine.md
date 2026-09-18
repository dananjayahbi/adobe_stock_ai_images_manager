# Service Specification: Deterministic QC Engine

| Field | Value |
|---|---|
| Document ID | SVC-QC-001 |
| Component | Deterministic Quality Control Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Run fast, zero-cost local heuristics on uploaded images before invoking any paid external APIs. This service acts as the first gate in the audit pipeline, rejecting obviously unsuitable files early to avoid unnecessary Gemini API expenditure.

## Responsibilities

The service accepts a single image file path as input and executes three deterministic checks sequentially. Each check must complete without throwing unhandled exceptions. The service returns early with a failure result if the image buffer is unreadable at any stage.

| Step | Check | Library | Description |
|---|---|---|---|
| 1 | Resolution / Megapixel Audit | Pillow | Open the image, read width and height dimensions, compute total megapixels by multiplying width by height and dividing by one million. |
| 2 | Edge Sharpness via Laplacian Variance | OpenCV | Convert the image to grayscale, apply the Laplacian operator, compute the variance of the resulting matrix. Higher variance indicates sharper edges. |
| 3 | Gibberish Text Detection | Tesseract OCR | Downscale the image to reduce processing time, run optical character recognition, analyze the extracted text for gibberish patterns using character uniqueness ratio. |

## Thresholds

| Metric | Threshold | Condition |
|---|---|---|
| Megapixels | >= 4.0 | Image must contain at least four million pixels to meet Adobe Stock minimum resolution requirements. |
| Laplacian Variance | >= 120.0 | Grayscale Laplacian variance must exceed this floor; values below indicate excessive blur or flat color fields. |
| OCR Text Length | > 4 characters | If recognized text exceeds four characters, trigger the character uniqueness ratio check. |
| Character Uniqueness Ratio | >= 40% | Count unique characters in the OCR output. Divide by total word length. If the ratio falls below 40%, flag as gibberish (repeated character noise typical of AI artifacts). |

## Output Contract

The service returns a dictionary with the following structure:

| Key | Type | Description |
|---|---|---|
| passed | Boolean | True only if all three checks meet their respective thresholds. False otherwise. |
| megapixels | Float | Computed megapixel value from step 1. |
| laplacian_variance | Float | Computed variance value from step 2. |
| reasons | List of Strings | Human-readable explanations for any failed check. Empty list when passed is true. |

## Constraints

- Return early with a failure result if the image buffer cannot be read or decoded. Do not proceed to subsequent checks.
- Never throw unhandled exceptions. All library calls must be wrapped so that failures produce a structured error response rather than crashing the calling thread.
- The service must remain synchronous and blocking only within its own execution context; it should not perform I/O outside of reading the provided file path.
- No network calls are permitted. This service is entirely local and offline.
- Temporary downscaled buffers for OCR must be held in memory and discarded immediately after use; never write intermediate files to disk.
| Field | Value |
|---|---|
| Document ID | SVC-QC-001 |
| Component | Deterministic Quality Control Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |