# Local Development Workflow

## Status

| Attribute | Value |
|---|---|
| Document Name | Local Development Workflow |
| Document Status | PENDING |
| Last Updated | 2026-09-18 |
| Scope | Operations - Environment Setup |

## Overview

This document outlines the prerequisites, startup sequence, and verification steps required to run the Adobe Stock AI Image Studio locally. The application relies on a decoupled architecture requiring both a Python backend and a Next.js frontend to operate simultaneously.

## System Prerequisites

Before initializing the project, the host machine must satisfy the following software requirements.

| Requirement | Minimum Version / Details |
|---|---|
| Python | 3.11 or higher |
| Node.js | 20 or higher |
| ExifTool | Latest binary installed and available on the system PATH |
| Tesseract OCR | Latest binary installed and available on the system PATH |
| Environment Variables | `GEMINI_API_KEY` must be set in the environment where the backend runs |

## Backend Startup Sequence

The backend is a FastAPI application responsible for image processing, quality control, and metadata embedding.

| Step | Action |
|---|---|
| 1 | Navigate to the backend directory via the terminal. |
| 2 | Create a new Python virtual environment. |
| 3 | Activate the newly created virtual environment. |
| 4 | Install all required dependencies from the `requirements.txt` file. The core dependencies include FastAPI, Uvicorn, Pillow, OpenCV-Python, Pytesseract, Google Generative AI SDK, and SQLAlchemy. |
| 5 | Start the development server by running Uvicorn targeting the `main:app` entry point. Ensure the reload flag is enabled for hot-reloading during development, and bind the server to port 8000. |

## Frontend Startup Sequence

The frontend is a Next.js application providing the operator dashboard.

| Step | Action |
|---|---|
| 1 | Open a separate terminal instance and navigate to the frontend directory. |
| 2 | Run the package manager install command to resolve and download all Node.js dependencies. |
| 3 | Start the Next.js development server using the standard development script. The server should initialize on the default port 3000. |

## Concurrent Execution Requirement

Both the backend terminal (port 8000) and the frontend terminal (port 3000) must remain open and running simultaneously. The frontend relies entirely on the backend API for data fetching, file uploads, and processing status updates. If either service is terminated, the local dashboard will cease to function correctly.

## Verification Steps

Once both services are running, perform the following checks to validate the environment:

| Step | Expected Outcome |
|---|---|
| 1 | Open a web browser and navigate to localhost on port 3000. The dark-themed dashboard should render without errors. |
| 2 | Drag a valid test JPEG image into the Dropzone component on the dashboard. |
| 3 | Observe the stats bar and image grid. A new record should appear in the grid, initially showing a Pending or Auditing status, confirming end-to-end communication between the frontend and backend. |
