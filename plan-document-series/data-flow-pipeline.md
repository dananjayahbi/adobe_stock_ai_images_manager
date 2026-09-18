# Data Flow Pipeline

This document defines the end-to-end lifecycle of an image as it moves through the Adobe Stock AI Image Studio. The pipeline is strictly ordered, transitioning assets through defined states: PENDING, AUDITING, PASSED, FLAGGED, and READY. Each step details the responsible component, the actions performed, and the resulting state change.

## Stage 1: Ingestion

**Trigger:** User interaction in the frontend.
**Responsible Components:** Frontend Dropzone, Backend Upload Route, File Service, Database.

1. The user drags one or more image files from their operating system and drops them into the Dropzone component in the browser interface.
2. The frontend client validates the file extensions locally to ensure only accepted formats are transmitted.
3. The frontend packages the valid files into a multipart HTTP POST request and sends it to the backend upload endpoint.
4. The backend receives the request stream. The file service writes the raw bytes directly to the `storage/inbox/` directory, preserving the original filename or generating a collision-safe unique identifier.
5. The file service reads the newly saved file and generates a downscaled, web-optimized thumbnail, saving it to the `storage/thumbnails/` directory.
6. The backend creates a new record in the SQLite database for each uploaded file. The initial status is set to **PENDING**. The record stores the inbox path, thumbnail path, original filename, and upload timestamp.
7. The backend returns a success response to the frontend, which updates the UI grid to display the new thumbnails with a PENDING status indicator.

## Stage 2: Deterministic Quality Control

**Trigger:** Background task execution following successful ingestion.
**Responsible Components:** Backend Background Worker, Deterministic QC Service, OpenCV, Pillow, Tesseract Binary, Database.

1. A background task scheduler picks up records with a PENDING status.
2. The worker updates the database record status from PENDING to **AUDITING**.
3. The deterministic QC service loads the image from the `storage/inbox/` directory using image processing libraries.
4. The service executes a sequence of mathematical and programmatic checks:
   - Calculates total pixel count (width multiplied by height) to verify minimum resolution requirements.
   - Applies a Laplacian operator to the grayscale representation of the image to calculate sharpness variance.
   - Inspects the image header metadata to verify the color space is sRGB.
   - Invokes the local Tesseract binary via the OCR wrapper to extract any visible text characters from the image.
5. If any deterministic check fails, the pipeline halts for this image. The worker updates the database status to **FLAGGED** and records the specific failure reasons (e.g., "Resolution below minimum threshold", "Laplacian variance too low", "Unintended text detected").
6. If all deterministic checks pass, the pipeline advances to Stage 3.

## Stage 3: Semantic Quality Control

**Trigger:** Successful completion of deterministic QC.
**Responsible Components:** Semantic QC Service, Gemini 2.5 Flash API, Database.

1. The semantic QC service reads the image from the `storage/inbox/` directory and encodes it for transmission.
2. The service constructs a structured prompt designed to evaluate commercial viability, anatomical correctness, and the presence of AI-specific artifacts.
3. The image data and prompt are transmitted over HTTPS to the Gemini 2.5 Flash API.
4. The API returns a structured JSON response containing an evaluation summary and a numerical confidence score representing the asset's quality.
5. The backend parses the response. If the confidence score is greater than or equal to 0.75, the database record status is updated to **PASSED**.
6. If the confidence score is below 0.75, or if the API explicitly identifies disqualifying artifacts, the database record status is updated to **FLAGGED**, and the AI's reasoning is stored in the failure reasons field.
7. The frontend periodically polls the backend (or receives updates) and refreshes the image grid, displaying confidence badges for PASSED images and detailed rejection reasons for FLAGGED images.

## Stage 4: Human Review and Approval

**Trigger:** User interaction in the frontend.
**Responsible Components:** Frontend Image Grid, Inspection Modal, Backend Action Routes, Database.

1. The user reviews the image grid in the browser. Images marked as PASSED display high confidence indicators.
2. The user may click a PASSED image to open the Inspection Modal, reviewing the full-resolution thumbnail, the semantic QC summary, and the confidence score.
3. The user clicks the approval action button (e.g., "Approve & Tag") either on an individual image or as a batch operation for multiple PASSED images.
4. The frontend sends an HTTP request to the backend action endpoint, providing the unique identifiers of the approved images.
5. The backend verifies that the requested images are currently in the PASSED state before proceeding.

## Stage 5: Metadata Generation and Packaging

**Trigger:** Receipt of human approval command.
**Responsible Components:** Metadata Service, Packaging Service, Gemini 2.5 Flash API, ExifTool Binary, File Service, Database.

1. The metadata service takes the approved image from the `storage/inbox/` directory and transmits it to the Gemini 2.5 Flash API with a prompt specifically engineered for Adobe Stock metadata generation.
2. The API returns a structured payload containing a commercially optimized title, a descriptive caption, and an array of relevant search keywords.
3. The backend temporarily stores this generated metadata in the corresponding database record.
4. The file service copies the original image from `storage/inbox/` to `storage/ready_to_upload/`. The original file in the inbox remains untouched.
5. The packaging service invokes the local ExifTool binary as a subprocess. It passes the file path of the copied image in the `ready_to_upload/` directory along with the generated title, description, and keywords formatted as IPTC and XMP tag arguments.
6. ExifTool embeds the metadata directly into the JPEG headers.
7. The packaging service queries the filesystem to verify the final file size of the embedded image remains within acceptable limits (under 45 MB).
8. Upon successful embedding and size verification, the backend updates the database record status to **READY**.
9. The frontend updates the UI to reflect that the image is fully processed and prepared for external submission.

## Stage 6: Manual External Upload

**Trigger:** User action outside the application.
**Responsible Components:** User, Operating System File Explorer, Adobe Stock Contributor Portal.

1. The user navigates to the `storage/ready_to_upload/` directory using their operating system's native file explorer.
2. The user selects the finalized JPEG files bearing the READY status.
3. The user manually uploads these files through the standard web interface of the Adobe Stock contributor portal.
4. During the portal submission, the user ensures the mandatory "Generative AI" checkbox is selected, as required by Adobe Stock policies. The studio prepares the batch for this manual check but does not automate the portal interaction itself.

## State Transition Summary

| Current State | Triggering Event | Next State | Condition |
| :--- | :--- | :--- | :--- |
| None | File uploaded to inbox | PENDING | Always |
| PENDING | Background worker starts | AUDITING | Always |
| AUDITING | Deterministic QC completes | FLAGGED | Any hard gate fails |
| AUDITING | Deterministic QC completes | AUDITING | All hard gates pass (proceeds to semantic) |
| AUDITING | Semantic QC completes | PASSED | Confidence >= 0.75 |
| AUDITING | Semantic QC completes | FLAGGED | Confidence < 0.75 or artifact detected |
| PASSED | User clicks Approve & Tag | READY | Metadata embedded successfully |
| FLAGGED | User overrides / retries | PENDING | Manual intervention (optional workflow) |