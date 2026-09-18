# Project Vision and Scope

## Executive Summary

The Adobe Stock AI Image Studio is a local desktop web application designed to automate the quality control, metadata generation, and preparation workflow for generative AI images destined for commercial sale on Adobe Stock. The system combines deterministic image analysis, multimodal AI evaluation, and human-in-the-loop review to ensure that every image submitted meets Adobe Stock's strict acceptance criteria. By orchestrating these stages in a streamlined pipeline, the studio eliminates manual guesswork and dramatically reduces the time creators spend preparing batches of images for upload.

The application consists of a FastAPI backend and a Next.js frontend, both running locally on the creator's machine. It interfaces with external services (Gemini 2.5 Flash API) and local binaries (ExifTool, Tesseract OCR) to perform its duties without requiring cloud-based file storage or remote processing of raw assets.

## Goals

- **Streamline Commercialization:** Provide a frictionless, repeatable process for transforming raw generative AI outputs into commercially viable, Adobe Stock-compliant assets.
- **Human-in-the-Loop Quality Assurance:** Ensure that no image is finalized for upload without explicit human approval, maintaining creative control and accountability.
- **Deterministic and Semantic QC:** Combine hard mathematical gates (resolution, sharpness, color space) with advanced AI semantic evaluation (artifact detection, text hallucination checks) to filter out non-compliant images early.
- **Automated Metadata Generation:** Leverage multimodal AI to generate highly relevant, search-optimized titles, keywords, and descriptions tailored to Adobe Stock's metadata requirements.
- **Standardized Embedding:** Automatically embed generated metadata into standard IPTC/XMP fields using ExifTool, ensuring the final files are fully prepared for portal upload.
- **Local-First Privacy:** Keep all original files, databases, and processing logic on the user's local machine, transmitting only necessary visual data to the AI API for analysis.

## Non-Goals

- **Mass Auto-Uploading:** This tool does not automatically push or upload images to Adobe Stock via API or browser automation. The final upload step remains a manual action performed by the user through the Adobe Stock contributor portal.
- **Vector Tracing or Conversion:** The system exclusively handles raster images (specifically JPEG). It does not perform vectorization, SVG conversion, or tracing of any kind.
- **Image Generation:** The studio is a post-processing and quality control tool. It does not generate, prompt, or render AI images itself.
- **Multi-Platform Distribution:** While metadata standards are broadly applicable, the specific constraints, baselines, and workflows are strictly optimized for Adobe Stock's current contributor guidelines, not other stock agencies.
- **Cloud Processing Pipeline:** The system is not designed as a distributed cloud service or SaaS platform. It is a single-user local desktop application.

## Target Users

The primary users are independent AI image creators, digital artists, and micro-stock contributors who generate batches of images using tools like Midjourney, Stable Diffusion, DALL-E, or Flux, and intend to monetize them on Adobe Stock. These users typically:

- Produce high volumes of images per session and need efficient batch filtering.
- Understand basic image concepts but lack the time to manually inspect every pixel-level detail or write extensive metadata.
- Require a reliable way to avoid account penalties or rejections caused by uploading low-quality, artifact-heavy, or improperly tagged AI-generated content.
- Operate on local workstations with sufficient resources to run a local web server and interact with system binaries.

## Success Metrics

| Metric | Target | Description |
| :--- | :--- | :--- |
| Acceptance Rate | Near 100% | Images that pass through the studio pipeline and are uploaded to Adobe Stock should almost never be rejected for technical or quality reasons. |
| Human Review Time | < 3 minutes per 50 images | The interface and pre-filtering must be efficient enough that a user can visually verify and approve a batch of 50 pre-audited images in under three minutes. |
| False Negative Rate | < 5% | High-quality images incorrectly flagged during deterministic or semantic QC should be minimal, preventing loss of viable commercial assets. |
| Metadata Relevance | High Contributor Satisfaction | Generated titles and keywords should require little to no manual editing before the user approves them. |
| System Stability | Zero Data Loss | The local database and file operations must reliably track state transitions without losing images or corrupting metadata during processing. |