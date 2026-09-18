# Tech Stack and Dependencies

This document specifies the exact technologies, libraries, system binaries, and external services required to build and operate the Adobe Stock AI Image Studio. All versions and selections are chosen to support a local, single-user desktop application architecture focused on image processing and AI integration.

## Runtime Environments

| Technology | Version Requirement | Purpose |
| :--- | :--- | :--- |
| Python | 3.11 or higher | The runtime environment for the backend server. Version 3.11+ is required to leverage modern asynchronous features, improved error messages, and native type hinting capabilities utilized by the web framework and data validation libraries. |
| Node.js | 20.0 or higher | The JavaScript runtime required to execute the frontend development server and build toolchain. Node 20+ ensures compatibility with the latest Next.js App Router features and modern ECMAScript standards. |

## Backend Framework and Server

| Dependency | Role | Description |
| :--- | :--- | :--- |
| FastAPI | Web Framework | A modern, high-performance Python web framework used to define the REST API routes. Selected for its native asynchronous support, automatic OpenAPI documentation generation, and deep integration with Pydantic for request/response validation. |
| Uvicorn | ASGI Server | A lightning-fast ASGI server implementation used to host the FastAPI application locally. It handles incoming HTTP requests, manages WebSocket connections if utilized for real-time updates, and orchestrates concurrent background tasks. |

## Backend Libraries

| Dependency | Role | Description |
| :--- | :--- | :--- |
| SQLAlchemy | ORM / Database Toolkit | Provides the Object-Relational Mapping layer between Python classes and the SQLite database. Handles schema definition, session management, query construction, and state persistence without requiring raw SQL strings in business logic. |
| Pillow (PIL) | Image Processing | The primary library for fundamental image manipulation. Used to read image headers, extract dimensions, verify color spaces, perform format conversions (e.g., normalizing to sRGB), and generate downscaled thumbnails for the frontend. |
| OpenCV (cv2) | Computer Vision | Utilized specifically for deterministic sharpness analysis. The library's implementation of the Laplacian operator is required to calculate the variance of pixel intensities, serving as the mathematical gate for rejecting blurry or out-of-focus AI generations. |
| pytesseract | OCR Wrapper | A Python binding for the Tesseract engine. Used during the deterministic QC phase to scan images for embedded text. The service logic evaluates the extracted text to detect and reject images containing AI-hallucinated gibberish or unintended watermarks. |
| google-genai | AI SDK | The official Python client library for interacting with Google's Generative AI models. Used to construct payloads, transmit image bytes, and parse structured JSON responses from the Gemini 2.5 Flash API for both semantic quality evaluation and metadata generation. |

## Frontend Framework and Libraries

| Dependency | Role | Description |
| :--- | :--- | :--- |
| Next.js | React Framework | Utilizes the App Router architecture to provide file-based routing, server-side rendering capabilities where appropriate, and a highly optimized local development experience. Serves as the structural foundation for the user interface. |
| React | UI Library | The core component model for building the interactive user interface. Manages local component state, handles user events (such as drag-and-drop uploads and approval clicks), and renders the visual representation of the image pipeline. |
| Axios | HTTP Client | A promise-based HTTP client used by the frontend to communicate with the local FastAPI backend. Configured with base URLs and interceptors to handle multipart form uploads for images and standard JSON requests for state retrieval and actions. |
| Tailwind CSS | Styling Engine | A utility-first CSS framework used to style the frontend components. Enables rapid, consistent UI development without maintaining separate stylesheet files, ensuring the dashboard, grids, and modals adhere to a unified design system. |
| Lucide React | Iconography | A library of consistent, lightweight SVG icons. Used throughout the interface to visually represent pipeline states, action buttons (approve, reject, inspect), and system status indicators without relying on external image assets. |

## System Binaries

The following executables must be installed on the host operating system and available via the system PATH environment variable. The backend invokes these directly as subprocesses.

| Binary | Requirement | Usage Context |
| :--- | :--- | :--- |
| ExifTool | Installed and on PATH | Invoked by the packaging service during the final pipeline stage. Receives command-line arguments containing file paths and metadata key-value pairs to write standardized IPTC and XMP tags directly into the JPEG headers of staged files. |
| Tesseract OCR | Installed and on PATH | Invoked by pytesseract during the deterministic QC stage. Processes image files to extract any visible text characters, which are subsequently analyzed by the backend to ensure compliance with Adobe Stock's restrictions on hallucinated text. |

## Database

| Technology | Configuration | Justification |
| :--- | :--- | :--- |
| SQLite | Local File-Based | Chosen for its zero-configuration, serverless nature. As a single-user local desktop application, the studio does not require the concurrency, network overhead, or administrative burden of a client-server database like PostgreSQL. The database exists as a single file within the project directory, simplifying backup, portability, and deployment. |

## External API Services

| Service | Integration Method | Purpose |
| :--- | :--- | :--- |
| Gemini 2.5 Flash | HTTPS via google-genai SDK | The sole external cloud dependency. Used for two distinct operations: multimodal semantic quality control (analyzing the visual content for artifacts and commercial viability) and automated metadata generation (producing titles, descriptions, and keywords). Requires a valid API key configured in the backend environment. |