# Backend Core Configuration Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - Core Infrastructure |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Centralize all environment variables, file paths, and threshold constants used across the backend pipeline. This module serves as the single source of truth for configuration, ensuring that no magic numbers or hardcoded paths exist elsewhere in the codebase.

## Responsibilities

### Environment Variable Loading

The configuration module must load the following required environment variable at startup:

| Variable Name | Type | Required | Description |
|---|---|---|---|
| GEMINI_API_KEY | String | Yes | API key for Google Gemini services used in semantic analysis and metadata generation |

If any required environment variable is missing, the application must fail fast during startup with a clear error message indicating which variable is absent. The system must not start in a degraded state when critical credentials are unavailable.

### Storage Directory Paths

All file storage paths must be defined using pathlib to ensure cross-platform compatibility. The following directories must be configured:

| Directory Key | Default Relative Path | Purpose |
|---|---|---|
| Inbox Directory | ./storage/inbox | Temporary holding area for newly uploaded images awaiting audit |
| Thumbnails Directory | ./storage/thumbnails | Generated thumbnail images for UI display |
| Ready to Upload Directory | ./storage/ready_to_upload | Final approved images with embedded metadata, prepared for Adobe Stock submission |

Each directory must be validated for existence at startup. If a directory does not exist, the system should create it automatically using pathlib operations.

### Quality Control Thresholds

The following numeric thresholds govern the automated auditing pipeline. These values must be exposed as named constants accessible throughout the application:

| Threshold Name | Value | Unit | Description |
|---|---|---|---|
| Minimum Megapixels | 4.0 | Megapixels | Absolute minimum resolution for an image to pass quality control |
| Recommended Megapixels Lower | 12.0 | Megapixels | Lower bound of the recommended resolution range for optimal Adobe Stock acceptance |
| Recommended Megapixels Upper | 25.0 | Megapixels | Upper bound of the recommended resolution range; beyond this may indicate unnecessarily large files |
| Laplacian Variance Minimum | 120.0 | Variance Score | Minimum sharpness score; images below this threshold are considered too blurry |
| Semantic Confidence Threshold | 0.75 | Ratio (0-1) | Minimum confidence score from AI analysis to accept generated metadata without human review |
| Maximum File Size | 45 | Megabytes | Hard upper limit for accepted uploads; files exceeding this are rejected |
| Target File Size Lower | 5 | Megabytes | Lower bound of the ideal file size range after processing |
| Target File Size Upper | 35 | Megabytes | Upper bound of the ideal file size range after processing |

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Fail fast on missing env vars | Raise a descriptive exception during application startup before any routes are registered |
| Use pathlib for all paths | All path construction, joining, and resolution must use pathlib.Path objects, never raw string concatenation |
| No scattered magic numbers | Any module needing a threshold or path must import it from this configuration module |
| Immutability | Configuration values must be loaded once at startup and treated as read-only for the lifetime of the process |