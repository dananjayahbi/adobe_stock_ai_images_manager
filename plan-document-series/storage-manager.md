# Service Specification: Storage Manager

| Field | Value |
|---|---|
| Document ID | SVC-STOR-006 |
| Component | File System Storage Operations Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Manage the three-tier directory structure used throughout the image processing pipeline. The storage manager handles file placement, thumbnail generation, promotion between directories, and cleanup operations while enforcing strict immutability guarantees on source files.

## Directory Structure

| Directory | Purpose | Contents |
|---|---|---|
| inbox | Landing zone for newly uploaded raw images | Original unmodified JPEG files awaiting audit |
| thumbnails | Web-optimized preview images for the frontend grid | 400x400 JPEG previews at quality 80, prefixed with thumb_ |
| ready_to_upload | Final verified and IPTC-tagged files approved for Adobe Stock submission | Copies of original files with embedded metadata |

## Responsibilities

| Responsibility | Description |
|---|---|
| Ensure Directories Exist | Create all three directories on application startup if they do not already exist. Use recursive creation to handle missing parent paths. |
| Generate Thumbnails | Read a source image from inbox, produce a scaled preview using Pillow's thumbnail method while maintaining aspect ratio, save as JPEG with quality 80 to the thumbnails directory. |
| Promote Files | Copy verified files from inbox to ready_to_upload, preserving the original filename exactly. |
| Clean Up Orphans | When a database record is deleted, remove the corresponding files from all three directories to prevent untracked disk consumption. |

## Thumbnail Generation Specification

| Parameter | Value |
|---|---|
| Maximum Dimensions | 400 pixels width by 400 pixels height |
| Aspect Ratio | Maintained; image is fit within the bounding box without cropping or distortion |
| Output Format | JPEG |
| Compression Quality | 80 (balances visual fidelity with file size for grid loading performance) |
| Naming Convention | Prefix thumb_ applied before the original filename (e.g., source "sunset.jpg" becomes "thumb_sunset.jpg") |
| Method | Pillow thumbnail method (not resize) to ensure proper downscaling behavior |

## File Operation Rules

| Operation | Source | Destination | Constraint |
|---|---|---|---|
| Upload ingest | Client upload stream | inbox/ | Write atomically using temporary file then rename to prevent partial reads by the QC engine |
| Thumbnail create | inbox/filename.jpg | thumbnails/thumb_filename.jpg | Never modify the source file; read-only access to inbox |
| Promotion copy | inbox/filename.jpg | ready_to_upload/filename.jpg | Preserve original filename exactly; copy rather than move to keep inbox as canonical source |
| Orphan cleanup | All three directories | Deleted | Only execute when explicitly triggered by record deletion; verify database record absence before removing files |

## Constraints

- Never modify original files in the inbox directory under any circumstances. The inbox serves as the immutable canonical source. All transformations produce outputs in other directories.
- Thumbnail naming must consistently apply the thumb_ prefix. The frontend grid component relies on this convention to construct image URLs without additional database lookups.
- File copy operations from inbox to ready_to_upload should use atomic patterns where the operating system supports them (write to temporary file, then rename) to prevent the ExifTool embedder from reading partially written files.
- Directory existence checks must run at startup, not lazily on first file operation. A missing directory during background processing causes silent failures in the audit pipeline.
- Orphan cleanup must verify that no database record references the file before deletion. Race conditions between upload completion and record creation could cause premature deletion of valid files.
- Disk space monitoring is not the responsibility of this service, but all operations should fail gracefully with structured error information if the filesystem reports insufficient space.
| Field | Value |
|---|---|
| Document ID | SVC-STOR-006 |
| Component | File System Storage Operations Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |