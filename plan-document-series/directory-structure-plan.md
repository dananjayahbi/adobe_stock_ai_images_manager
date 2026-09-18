# Directory Structure Plan

This document defines the complete file and directory tree for the Adobe Stock AI Image Studio. The structure is divided into two primary domains: the Python FastAPI backend and the Next.js frontend. Every path listed below includes an annotation describing its specific purpose within the system. No code is contained in this document; it serves purely as a structural blueprint.

## Complete File Tree

```text
adobe_stock_ai_images_manager/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── routes_upload.py
│   │   │   ├── routes_images.py
│   │   │   └── routes_actions.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── database.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── image_record.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── image_schema.py
│   │   │   └── upload_schema.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── file_service.py
│   │   │   ├── deterministic_qc_service.py
│   │   │   ├── semantic_qc_service.py
│   │   │   ├── metadata_service.py
│   │   │   └── packaging_service.py
│   │   └── __init__.py
│   ├── storage/
│   │   ├── inbox/
│   │   ├── thumbnails/
│   │   └── ready_to_upload/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── Dropzone.tsx
│   │   │   ├── ImageGrid.tsx
│   │   │   ├── InspectionModal.tsx
│   │   │   └── StatsBar.tsx
│   │   └── lib/
│   │       └── api_client.ts
│   ├── package.json
│   └── tailwind.config.js
└── plan-document-series/
```

## Backend Structure Annotations

### Root Files

| Path | Purpose |
| :--- | :--- |
| `backend/main.py` | The ASGI application entry point. Responsible for initializing the FastAPI application instance, mounting the API routers, configuring middleware (such as CORS for local frontend communication), and triggering the creation of necessary storage directories on startup. |
| `backend/requirements.txt` | A flat list of all Python dependencies required to run the backend server, including exact version pins to ensure deterministic environments. |

### Application Package (`backend/app/`)

#### API Layer (`app/api/`)
This directory contains the REST route definitions. It acts as the interface between the HTTP layer and the internal business logic.

| Path | Purpose |
| :--- | :--- |
| `routes_upload.py` | Handles incoming multipart form data requests for image uploads. Validates file extensions, delegates file saving to the file service, and initiates the background processing pipeline. |
| `routes_images.py` | Provides endpoints for retrieving lists of images, fetching individual image records with their current status (PENDING, AUDITING, PASSED, FLAGGED, READY), and serving generated thumbnails to the frontend. |
| `routes_actions.py` | Exposes endpoints for user-triggered actions, specifically the approval command that transitions an image from PASSED to the metadata generation and packaging stages. |

#### Core Configuration (`app/core/`)
Contains foundational setup modules required by the rest of the application.

| Path | Purpose |
| :--- | :--- |
| `config.py` | Centralizes all configuration variables, including filesystem paths for storage directories, external API keys, binary paths for ExifTool and Tesseract, and QC threshold values. Reads from environment variables or local configuration files. |
| `database.py` | Manages the SQLite database connection lifecycle. Configures the Object-Relational Mapping engine, establishes session factories, and handles connection pooling appropriate for a local, single-user application. |

#### Data Models (`app/models/`)
Defines the database schema representations using ORM classes.

| Path | Purpose |
| :--- | :--- |
| `image_record.py` | Defines the primary database table structure for tracking images. Includes columns for unique identifiers, original filenames, filesystem paths, current pipeline status, deterministic QC results, semantic QC confidence scores, failure reasons, generated metadata fields, and timestamps. |

#### Validation Schemas (`app/schemas/`)
Contains Pydantic models used for strict request and response validation.

| Path | Purpose |
| :--- | :--- |
| `image_schema.py` | Defines the shape of image data returned to the frontend via API responses. Ensures that only expected fields, properly typed and formatted, leave the backend. |
| `upload_schema.py` | Defines the validation rules for incoming upload requests, ensuring metadata accompanying file uploads conforms to expected structures. |

#### Business Logic Services (`app/services/`)
The core processing engines of the application. Routes delegate all heavy lifting to these modules.

| Path | Purpose |
| :--- | :--- |
| `file_service.py` | Manages all direct interactions with the local filesystem. Handles writing uploaded bytes to the inbox, generating web-optimized thumbnails, copying files between storage directories, and verifying file integrity. |
| `deterministic_qc_service.py` | Executes programmatic, non-AI quality checks. Invokes image processing libraries to measure resolution, calculate sharpness variance, verify color spaces, and calls the Tesseract binary to scan for unwanted text. Returns structured pass/fail results with specific rejection reasons. |
| `semantic_qc_service.py` | Manages communication with the Gemini 2.5 Flash API for visual analysis. Formats prompts, transmits image data, parses the AI's structured JSON responses, extracts confidence scores, and determines if the image meets the threshold for a PASSED state. |
| `metadata_service.py` | Interacts with the Gemini API specifically for content tagging. Generates commercially optimized titles, descriptions, and keyword arrays based on the visual content of approved images. |
| `packaging_service.py` | Orchestrates the final preparation stage. Takes generated metadata, invokes the ExifTool binary as a subprocess to embed IPTC and XMP tags into a copy of the image, verifies the final file size constraints, and places the completed asset into the ready-to-upload directory. |

### Storage Directories (`backend/storage/`)

These directories are created automatically by the application on startup if they do not exist. They represent the physical stages of the image pipeline.

| Path | Purpose |
| :--- | :--- |
| `inbox/` | The landing zone for raw, unmodified user uploads. Files here serve as the immutable source of truth during the auditing phases. |
| `thumbnails/` | Stores downscaled, compressed JPEG previews generated from inbox files. These are served to the frontend to allow rapid UI rendering without transferring large raw files over the local network. |
| `ready_to_upload/` | The final destination for processed assets. Contains fully tagged, color-normalized, and size-verified JPEG files that have achieved the READY status and await manual upload to Adobe Stock by the user. |

## Frontend Structure Annotations

### Root Files

| Path | Purpose |
| :--- | :--- |
| `frontend/package.json` | Defines the Node.js project metadata, scripts for development and building, and lists all required JavaScript dependencies. |
| `frontend/tailwind.config.js` | Configures the Tailwind CSS framework, defining design tokens, theme extensions, and content paths for utility class generation. |

### Source Directory (`frontend/src/`)

#### Application Router (`src/app/`)
Utilizes the Next.js App Router paradigm for routing and layout management.

| Path | Purpose |
| :--- | :--- |
| `layout.tsx` | Defines the root HTML structure, global providers, and persistent UI shell that wraps all pages in the application. |
| `page.tsx` | The primary dashboard view. Composes the main interface by integrating the dropzone, statistics bar, and image grid into a unified workspace. |
| `globals.css` | Contains base CSS resets, Tailwind directives, and any global styling rules applied across the entire frontend. |

#### UI Components (`src/components/`)
Encapsulated, reusable React components that form the user interface.

| Path | Purpose |
| :--- | :--- |
| `Dropzone.tsx` | A drag-and-drop interaction zone. Listens for file system drop events, validates file types client-side, displays upload progress indicators, and transmits files to the backend upload endpoint. |
| `ImageGrid.tsx` | A responsive layout component that fetches and displays image thumbnails. Renders visual status badges corresponding to the PENDING, AUDITING, PASSED, FLAGGED, and READY states, and provides interactive elements for user approvals. |
| `InspectionModal.tsx` | An overlay dialog triggered when a user selects a specific image. Displays high-resolution previews, detailed audit failure reasons, semantic confidence scores, and editable fields for generated metadata prior to final packaging. |
| `StatsBar.tsx` | A summary header component that aggregates and displays real-time counts of images in each pipeline state, providing the user with immediate operational awareness of batch progress. |

#### Utilities (`src/lib/`)

| Path | Purpose |
| :--- | :--- |
| `api_client.ts` | A centralized HTTP client module configured to communicate with the local FastAPI backend. Encapsulates base URLs, request headers, timeout configurations, and provides typed functions for every backend endpoint consumed by the frontend components. |