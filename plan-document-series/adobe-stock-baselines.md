# Adobe Stock Baselines

This document maps the specific acceptance criteria and technical constraints enforced by the Adobe Stock contributor platform to the automated enforcement mechanisms implemented within the Adobe Stock AI Image Studio. Every baseline listed below represents a hard requirement for commercial viability; the studio's pipeline is designed to guarantee compliance before an asset reaches the READY state.

## Criteria Mapping Table

| Adobe Stock Criterion | Studio Enforcement Mechanism | Pipeline Stage | Behavior on Failure |
| :--- | :--- | :--- | :--- |
| **File Format** | Strict validation of file headers and extensions. Only JPEG baseline RGB files are accepted. Progressive JPEGs, PNGs, WebP, and TIFFs are rejected at ingestion. | Upload / Deterministic QC | Status set to FLAGGED. Reason: "Unsupported or invalid file format." |
| **Minimum Resolution** | Mathematical calculation of total pixel count (width multiplied by height). The absolute minimum gate is 4.0 Megapixels. Images between 4.0 MP and 12.0 MP are passed but noted as suboptimal. | Deterministic QC | Status set to FLAGGED. Reason: "Resolution below 4.0 MP minimum threshold." |
| **Maximum File Size** | Filesystem byte inspection. The absolute maximum allowed by Adobe Stock is 45 MB. The studio targets a compressed output range of 5 MB to 35 MB to ensure safety margins during metadata embedding. | Packaging | Metadata embedding aborted. Status remains PASSED but packaging fails. User notified of size constraint violation. |
| **Color Space** | Header metadata inspection via image processing libraries. If AdobeRGB, Display P3, or CMYK profiles are detected, the system automatically converts the color space to sRGB before further processing. | Deterministic QC / Packaging | Auto-converted to sRGB. No failure state triggered unless conversion corrupts the file. |
| **Sharpness** | Application of a Laplacian operator to the grayscale representation of the image. The resulting variance score must be greater than or equal to 120.0. This filters out blurry, soft, or heavily artifacted AI generations. | Deterministic QC | Status set to FLAGGED. Reason: "Laplacian variance below 120.0; image too soft." |
| **Text / Gibberish** | Optical Character Recognition scan using the local Tesseract binary. Extracted strings are analyzed for non-dictionary characters, fragmented words, or hallucinated glyphs commonly produced by generative models. | Deterministic QC | Status set to FLAGGED. Reason: "Unintended text or AI-hallucinated gibberish detected." |
| **Generative AI Tagging** | Workflow preparation. Adobe Stock mandates that contributors check a specific "Generative AI" portal checkbox during upload. The studio does not automate the portal click, but it batches and organizes READY files specifically to remind the user to perform this manual check. | Post-READY (Manual) | N/A (User responsibility). UI displays reminder badge for READY assets. |
| **Queue Limit** | Throttling mechanism in the backend scheduler. New Adobe Stock contributor accounts typically have a pending review limit of approximately 50 images. The studio tracks the number of READY files and pauses batch packaging if the local staging directory exceeds safe thresholds relative to the user's known upload cadence. | Packaging | Background task paused. Status remains PASSED until queue pressure decreases. |

## Detailed Enforcement Specifications

### Resolution Gates

The resolution check operates on two tiers. The hard gate enforces the absolute minimum required by Adobe Stock. Any image failing this gate is immediately disqualified.

- **Hard Gate:** $width \times height \ge 4{,}000{,}000$ pixels.
- **Recommended Target:** $width \times height \ge 12{,}000{,}000$ pixels.

Images passing the hard gate but falling below the recommended target are permitted to proceed through the pipeline, as they remain commercially viable, though they may yield lower search visibility on the platform.

### Sharpness Threshold Rationale

Generative AI models frequently produce images that appear structurally sound at thumbnail scale but exhibit micro-blurring, smeared textures, or inconsistent focus upon close inspection. The Laplacian variance threshold of 120.0 serves as a mathematical proxy for high-frequency detail. Images scoring below this value lack the edge contrast required for commercial stock photography and are systematically filtered out during deterministic QC to prevent wasting API calls on visually defective assets.

### Text and Gibberish Detection

AI image generators struggle significantly with rendering legible typography. They frequently produce signs, labels, or background elements containing pseudo-text—characters that resemble letters but form no valid words. Adobe Stock reviewers reject images containing unintended, illegible text. The studio mitigates this by running Tesseract OCR over the entire image canvas. If the engine returns character sequences that fail basic dictionary validation or entropy checks, the image is flagged. Intentional text (e.g., a generated poster with perfect spelling) is rare in standard stock workflows; thus, aggressive filtering is preferred over false negatives.

### Queue Limit Management

Adobe Stock employs human reviewers alongside automated systems. Flooding a new contributor account with hundreds of uploads simultaneously triggers algorithmic scrutiny and increases rejection rates. The studio respects this operational reality by implementing a soft throttle. While the local database can hold thousands of records, the transition from PASSED to READY (which involves copying files to the final upload directory) is governed by a configurable batch limit. Users are encouraged to upload and clear their READY directories in controlled increments of approximately 50 assets.

### Generative AI Disclosure Compliance

Adobe Stock's terms of service strictly require contributors to disclose when an asset is created using generative AI tools. Failure to do so results in account suspension. Because the studio cannot interact directly with the Adobe Stock web portal, it fulfills its responsibility by ensuring all processed files are perfectly staged in the `ready_to_upload/` directory, and the frontend interface prominently surfaces reminders that the Generative AI disclosure checkbox must be manually selected during the external upload process.