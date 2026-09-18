# Service Specification: ExifTool IPTC/XMP Embedder

| Field | Value |
|---|---|
| Document ID | SVC-EXIF-004 |
| Component | Metadata Injection Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |

## Purpose

Embed generated commercial metadata directly into JPEG files using ExifTool as a subprocess. This service writes both IPTC and XMP tags simultaneously to ensure maximum compatibility with Adobe Stock's ingestion pipeline and downstream digital asset management systems.

## Responsibilities

| Responsibility | Description |
|---|---|
| Verify Prerequisites | Confirm ExifTool is available on the system PATH during service startup. Fail loudly at initialization rather than silently at runtime. |
| Resolve Absolute Path | Convert the provided file path to an absolute path before constructing the command to prevent working directory ambiguity. |
| Construct Command Array | Build the ExifTool argument list including the overwrite_original flag to prevent accumulation of backup files. |
| Set Title Tags | Write the generated title to IPTC:ObjectName, IPTC:Caption-Abstract, XMP:Title, and XMP:Description simultaneously. |
| Set Keyword Tags | Iterate through the keywords list (maximum 35) and set each keyword on both IPTC:Keywords and XMP:Subject. |
| Execute Subprocess | Run the constructed command, capturing standard output and standard error streams independently. |
| Evaluate Result | Return a boolean success indicator based on the process exit code being exactly zero. |

## Tag Mapping Table

| Source Field | IPTC Tag | XMP Tag | Notes |
|---|---|---|---|
| Title | ObjectName | Title | Written to both namespaces for redundancy. |
| Title | Caption-Abstract | Description | Duplicate of title used as description per Adobe Stock convention. |
| Keywords (each) | Keywords | Subject | One tag pair per keyword entry. Maximum 35 iterations. |

## Command Construction Rules

- The overwrite_original flag must always be present. Without it, ExifTool creates numbered backup files that consume disk space and clutter the ready_to_upload directory.
- All tag assignments must use the equals-sign syntax within the argument array, not separate flag-value pairs, to prevent shell interpretation issues on Windows.
- The file path must be the final argument in the command array.
- Keyword arguments must be added individually rather than as a comma-separated string to preserve keywords that legitimately contain commas.

## Execution Constraints

- Capture both stdout and stderr from the subprocess. Do not allow output to leak to the console.
- Return boolean true only when the subprocess exit code is exactly 0. Any non-zero exit code constitutes failure.
- On failure, log the captured stderr content at error level for debugging. Do not discard it.
- Resolve the target file to an absolute path before execution. Relative paths introduce nondeterminism depending on the working directory of the background task runner.
- Verify ExifTool exists on PATH at service initialization time. If missing, raise a startup error that prevents the application from accepting uploads into a state where metadata embedding will inevitably fail.
- Never modify the source file in the inbox directory. This service operates exclusively on copies residing in the ready_to_upload directory.
- Subprocess execution must have a timeout to prevent indefinite hangs if ExifTool encounters a corrupted file structure.
| Field | Value |
|---|---|
| Document ID | SVC-EXIF-004 |
| Component | Metadata Injection Service |
| Status | PENDING |
| Last Updated | 2026-09-18 |
| Layer | Backend Services |