# System Architecture Overview

## High-Level Component Description

The Adobe Stock AI Image Studio is a locally hosted, two-tier web application consisting of a Next.js frontend and a FastAPI backend. All components run on the user's local machine. The architecture is designed to process images through a staged pipeline, moving assets from raw uploads to fully tagged, commercially ready files while maintaining strict state tracking in a local database.

### Frontend: Next.js Local Application

The frontend is a Next.js application utilizing the App Router architecture. It serves as the primary human-in-the-loop interface for the studio. Its responsibilities include:

- **Real-Time Status Presentation:** Continuously polling or receiving updates regarding the processing status of images (PENDING, AUDITING, PASSED, FLAGGED, READY).
- **Confidence Badges:** Displaying visual indicators that represent the AI's confidence score during semantic quality control, allowing users to quickly gauge asset viability.
- **One-Click Approvals:** Providing streamlined interaction patterns where users can approve passed images and trigger metadata generation with minimal friction.
- **Visual Review Interfaces:** Rendering grids and modal views for inspecting high-resolution thumbnails, reviewing flagged reasons, and editing generated metadata before final embedding.

### Backend: FastAPI Local Server

The backend is a Python FastAPI application running via an ASGI server (Uvicorn). It acts as the central orchestrator for all business logic, file system operations, and external integrations. The backend processes images through a strictly ordered, staged pipeline:

1. **Deterministic QC Stage:** Executes mathematical and programmatic checks on the image file. This includes resolution validation, sharpness analysis via Laplacian variance, color space verification, and optical character recognition (OCR) scans for hallucinated text. This stage requires no external API calls.
2. **Multimodal Semantic QC Stage:** If deterministic checks pass, the backend transmits the image data to the Gemini 2.5 Flash API. This stage evaluates the image for AI-specific artifacts, anatomical correctness, aesthetic quality, and overall commercial viability.
3. **Packaging and Tagging Stage:** Upon human approval of a passed image, the backend invokes the Gemini API again to generate descriptive titles, keywords, and categories. It then copies the original file to a staging directory and uses ExifTool to embed this metadata into standard IPTC and XMP fields.

### Database: SQLite

The system utilizes a local SQLite database managed via an Object-Relational Mapper (ORM). The database is responsible for:

- Persisting the lifecycle state of every image record.
- Storing deterministic and semantic audit results, including specific failure reasons and confidence scores.
- Caching generated metadata (titles, descriptions, keyword lists) prior to embedding.
- Maintaining timestamps for upload, state transitions, and final packaging.

### Local Filesystem Storage Directories

The backend manages three distinct directories on the local filesystem to enforce separation of concerns across the pipeline:

| Directory | Purpose |
| :--- | :--- |
| Inbox | Receives and stores the original, unmodified raw uploads directly from the user. Files here are never altered by the system. |
| Thumbnails | Stores web-optimized, downscaled preview images generated from inbox files. These are served to the frontend to ensure rapid grid rendering without transmitting heavy raw files. |
| Ready to Upload | Stores the final, processed JPEG files that have successfully passed all QC stages, received human approval, and had their metadata embedded. Files here are prepared for manual upload to Adobe Stock. |

### External Dependencies

The backend relies on three external dependencies to fulfill its processing requirements:

- **Gemini 2.5 Flash API:** An external multimodal AI service accessed via the official SDK. Used exclusively for semantic quality evaluation and metadata generation. Requires an active internet connection and valid API credentials.
- **ExifTool Binary:** A local command-line utility required for reading, writing, and manipulating image metadata. The backend invokes this binary as a subprocess to embed IPTC and XMP tags into the final JPEG files.
- **Tesseract OCR Binary:** A local optical character recognition engine. The backend invokes this binary during the deterministic QC stage to scan images for unintended text or AI-hallucinated gibberish.

## Data Flow Direction

The directional flow of data between components follows a strict sequence:

1. **User to Frontend:** The user interacts with the browser, dragging and dropping image files into the designated upload zone.
2. **Frontend to Backend (Upload):** The frontend packages the files into a multipart HTTP POST request and transmits them to the backend's upload endpoint.
3. **Backend to Filesystem:** The backend writes the raw files to the inbox directory and generates corresponding thumbnails in the thumbnails directory.
4. **Backend to Database:** The backend creates a new record for each image, initializing its state to PENDING.
5. **Backend Internal Processing:** Background tasks transition the database state to AUDITING. The backend reads files from the inbox, runs deterministic algorithms, and updates the database with results.
6. **Backend to External API (Semantic QC):** For images passing deterministic QC, the backend sends image data over HTTPS to the Gemini API and receives structured JSON evaluations.
7. **Database State Update:** Based on API responses, the backend updates the record state to either PASSED or FLAGGED.
8. **Backend to Frontend (State Sync):** The frontend requests current states from the backend via REST endpoints and updates the UI to reflect PASSED or FLAGGED statuses with associated confidence badges or failure reasons.
9. **Frontend to Backend (Approval):** The user clicks an approval action in the frontend, sending an HTTP request to the backend to initiate the tagging phase.
10. **Backend to External API (Metadata):** The backend queries the Gemini API for title, description, and keyword generation based on the approved image.
11. **Backend to Filesystem (Staging):** The backend copies the approved file from the inbox to the ready-to-upload directory.
12. **Backend to ExifTool:** The backend passes the copied file path and generated metadata to the ExifTool binary via subprocess execution.
13. **Database Final Update:** Upon successful embedding, the backend updates the database record state to READY.
14. **Filesystem to User:** The user accesses the ready-to-upload directory via their operating system's file explorer and manually uploads the finalized assets to the Adobe Stock contributor portal.