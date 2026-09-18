# File Format Constraints

This document provides the detailed technical specification for file format handling, color space normalization, dimension validation, and file size management within the Adobe Stock AI Image Studio. These constraints are enforced programmatically during the deterministic quality control and packaging stages to ensure absolute compliance with Adobe Stock's ingestion requirements.

## Accepted File Types

The system strictly limits accepted uploads to a single image format. No other formats are permitted at any stage of the pipeline.

| Extension | MIME Type | Acceptance Status |
| :--- | :--- | :--- |
| `.jpg` | `image/jpeg` | Accepted |
| `.jpeg` | `image/jpeg` | Accepted |
| All others (`.png`, `.webp`, `.tiff`, etc.) | Any | Rejected at upload |

Any file submitted without a `.jpg` or `.jpeg` extension, or any file whose internal binary header does not match the JPEG signature regardless of its extension, must be rejected immediately. The database record is created solely to log the rejection, and the status is set directly to FLAGGED with the reason indicating an invalid file format.

## JPEG Encoding Constraints

Adobe Stock requires specific internal encoding parameters for JPEG files. The studio must validate and, where necessary, re-encode files to meet these standards before they reach the READY state.

### Baseline vs. Progressive

Only baseline (standard) JPEG encoding is accepted. Progressive JPEGs, which load in successive passes, are explicitly prohibited by Adobe Stock's automated ingestion systems. During the deterministic QC stage, the backend must inspect the Start of Frame (SOF) marker in the JPEG header. If the SOF marker indicates progressive encoding, the file must either be rejected and flagged, or automatically re-encoded as a baseline JPEG during the packaging stage. Automatic re-encoding is preferred to preserve viable assets that merely used the wrong export setting.

### Chroma Subsampling and Color Mode

The JPEG must be encoded in the RGB color mode. CMYK JPEGs are not supported by the target platform and will cause immediate rejection. Grayscale images are also excluded from this workflow, as commercial stock photography requires full color channels. The system must verify that the image contains exactly three color channels corresponding to Red, Green, and Blue.

## Color Space Normalization

Generative AI tools frequently output images embedded with wide-gamut color profiles such as Display P3 or Adobe RGB. While visually superior on supported monitors, Adobe Stock mandates that all uploaded assets utilize the sRGB color space to ensure consistent rendering across all buyer devices.

### Detection

During the deterministic QC stage, the image processing library must read the embedded ICC profile of the JPEG. The system categorizes the profile into one of three states:

1. **sRGB:** The file meets the requirement. No action is taken.
2. **Adobe RGB / Display P3 / Other Wide Gamut:** The file requires normalization.
3. **Missing Profile:** The system assumes sRGB by default, but explicitly tags the file metadata to indicate an untagged color space if required by downstream processes.

### Conversion Behavior

If a non-sRGB profile is detected, the conversion process occurs during the packaging stage, immediately prior to metadata embedding. The backend must use a color management engine to map the wide gamut pixels into the sRGB gamut using a perceptual or relative colorimetric rendering intent. This prevents harsh clipping of out-of-gamut colors while ensuring the final pixel values conform to the sRGB standard. The new sRGB ICC profile is then embedded into the file, replacing the original wide-gamut profile.

## Dimension and Resolution Validation

Resolution is evaluated purely as a mathematical product of the image's pixel dimensions. The backend extracts the width and height from the image header without loading the entire pixel array into memory when possible.

### Hard Minimum Gate

The absolute minimum resolution required by Adobe Stock is 4.0 Megapixels. This is calculated using the formula:

$$width \times height \ge 4{,}000{,}000$$

Any image failing to meet this exact threshold is immediately transitioned to the FLAGGED state during deterministic QC. No exceptions or overrides are permitted for this constraint.

### Recommended Commercial Target

While 4.0 MP satisfies the hard gate, images in this lower tier perform poorly in commercial search rankings compared to higher-resolution assets. The studio defines a recommended target range for optimal commercial value:

- **Minimum Recommended:** 15.0 Megapixels ($15{,}000{,}000$ pixels)
- **Maximum Recommended:** 25.0 Megapixels ($25{,}000{,}000$ pixels)

Images falling between the hard minimum (4.0 MP) and the recommended minimum (15.0 MP) are allowed to pass through the pipeline, but the frontend interface should display a visual advisory badge indicating suboptimal resolution. Images exceeding 25.0 MP are acceptable but may require more aggressive compression to satisfy file size constraints.

## File Size Management

File size constraints apply to the final packaged asset sitting in the `ready_to_upload/` directory, after all metadata has been embedded and color spaces normalized.

### Absolute Maximum Limit

Adobe Stock enforces a hard maximum file size of 45 MB. Any file exceeding this limit upon upload to their portal is rejected. The studio must guarantee that no file reaches the READY state if its byte size exceeds 45,000,000 bytes.

### Target Compression Range

To provide a safety margin against filesystem reporting discrepancies and to optimize download speeds for buyers, the studio targets a compressed file size range of 5 MB to 35 MB. 

### Post-Embedding Verification Workflow

The process of embedding IPTC and XMP metadata via ExifTool can occasionally inflate a file's byte size, particularly if large keyword arrays are written or if the tool alters the internal JPEG structure. Therefore, file size verification must occur *after* ExifTool completes its execution, not before.

1. The packaging service copies the inbox file to the ready-to-upload directory.
2. Color space normalization is applied if required.
3. ExifTool embeds the generated metadata.
4. The packaging service queries the operating system for the exact byte size of the finalized file.
5. If the size is between 5 MB and 35 MB, the file is accepted.
6. If the size is between 35 MB and 45 MB, the file is accepted but flagged internally for review.
7. If the size exceeds 45 MB, the packaging service must re-process the file. It invokes the image processing library to re-save the JPEG with a reduced compression quality parameter. This reduction loop continues iteratively until the file falls below the 45 MB absolute maximum.
8. If reducing the compression quality degrades the image sharpness below the Laplacian variance threshold of 120.0 defined in the baselines, the system faces a conflict between size and quality. In this scenario, the asset cannot be safely packaged; it remains in the PASSED state, and the user is notified via the frontend that manual intervention is required to balance size and quality.

## Summary of Constraints Table

| Parameter | Constraint | Enforcement Stage | Action on Violation |
| :--- | :--- | :--- | :--- |
| File Extension | `.jpg` or `.jpeg` only | Upload | Reject immediately, set FLAGGED |
| Internal Format | Valid JPEG binary header | Upload | Reject immediately, set FLAGGED |
| Encoding Type | Baseline (non-progressive) | Deterministic QC / Packaging | Auto-re-encode or set FLAGGED |
| Color Mode | RGB (3 channels) | Deterministic QC | Set FLAGGED if CMYK/Grayscale |
| Color Space | sRGB | Packaging | Auto-convert from AdobeRGB/P3 |
| Minimum Pixels | $width \times height \ge 4{,}000{,}000$ | Deterministic QC | Set FLAGGED |
| Target Pixels | $15{,}000{,}000$ to $25{,}000{,}000$ | Frontend Display | Show advisory badge if outside range |
| Max File Size | < 45 MB | Packaging (Post-ExifTool) | Iteratively reduce compression quality |
| Target File Size | 5 MB to 35 MB | Packaging | Adjust compression quality parameter |