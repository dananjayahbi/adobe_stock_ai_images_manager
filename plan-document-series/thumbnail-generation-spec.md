# Thumbnail Generation Specification

## Purpose

This document defines the process for creating web-optimized preview images from uploaded source files. Thumbnails reduce bandwidth consumption and improve frontend rendering performance by avoiding full-resolution image loads in grid views.

## Status

PENDING

## Input Specification

| Property | Value |
|---|---|
| Source Format | JPEG files located in the inbox directory |
| Source Resolution | Full original resolution as uploaded by the user |
| Color Space | Preserved from source image |

## Processing Pipeline

The thumbnail generation process follows these sequential steps:

| Step | Operation | Details |
|---|---|---|
| 1 | Open source | Load the JPEG file from the inbox directory using the Pillow imaging library |
| 2 | Apply thumbnail method | Use the built-in thumbnail operation with a 400x400 bounding box |
| 3 | Maintain aspect ratio | The thumbnail method must preserve the original proportions without cropping or distortion |
| 4 | Save output | Write the result as a JPEG file with quality setting of 80 to the thumbnails directory |

## Output Specification

| Property | Value |
|---|---|
| Maximum Dimensions | 400 pixels width by 400 pixels height |
| Aspect Ratio | Preserved from source; image fits within bounding box without stretching |
| Output Format | JPEG |
| Compression Quality | 80 out of 100 |
| Output Directory | Dedicated thumbnails folder within the project storage structure |

## Naming Convention

Generated thumbnails must prepend the prefix "thumb_" to the original filename. For example, if the source file is named "landscape_sunset.jpg", the thumbnail must be named "thumb_landscape_sunset.jpg". This convention allows straightforward mapping between source records and their preview assets.

## Frontend Usage

The ImageGrid component in the Next.js frontend loads thumbnails through static file serving provided by the backend. Each record object contains a thumbnail path field that the frontend uses as the image source attribute. This approach provides the following benefits:

| Benefit | Description |
|---|---|
| Bandwidth reduction | Thumbnails are significantly smaller than multi-megapixel originals |
| Faster rendering | Grid layouts with dozens of images load without layout shift delays |
| Consistent sizing | Bounding box constraint ensures uniform card heights in the grid |

## Timing Constraint

Thumbnail generation must occur synchronously during the upload request lifecycle. The backend must complete thumbnail creation before returning the HTTP response to the client. This ensures that when the frontend receives confirmation of the upload, the thumbnail is already available for immediate display without requiring a secondary fetch or delayed loading state.

## Error Handling

If the source image cannot be read or processed by the imaging library, the system must follow this fallback behavior:

| Condition | Action |
|---|---|
| Source file is corrupted or unreadable | Skip thumbnail generation without raising a fatal error |
| Pillow throws an exception during open | Catch the exception, log the failure, proceed with record creation |
| Pillow throws an exception during save | Catch the exception, log the failure, proceed with record creation |

In all failure cases, the image record must still be created in the database. The thumbnail path field for that record must point to a predefined placeholder image rather than being left null or empty. This ensures the frontend ImageGrid component always has a valid image source to render, maintaining visual consistency even when individual thumbnails fail to generate.

## Placeholder Specification

| Property | Value |
|---|---|
| Location | Static assets directory served by the backend |
| Appearance | Neutral visual indicator that thumbnail generation failed |
| Format | JPEG matching the expected thumbnail dimensions |
| Path Assignment | Set as the thumbnail_path value when generation is skipped |