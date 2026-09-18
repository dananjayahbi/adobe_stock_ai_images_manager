# Deployment and Packaging Specification

## Purpose

This document defines how the Adobe Stock AI Image Studio application is packaged, configured, and started for daily local use. It covers environment preparation, dependency installation, process startup, and system verification.

## Status

PENDING

## Backend Deployment

### Virtual Environment Setup

A Python virtual environment must be created within the project root to isolate dependencies from the system Python installation. The virtual environment directory must be excluded from version control.

### Dependency Installation

All Python packages listed in the requirements manifest must be installed into the activated virtual environment. Installation should be performed using the standard Python package manager with the requirements file as input.

### Server Startup

The FastAPI backend must be served using the Uvicorn ASGI server with the following configuration:

| Parameter | Value |
|---|---|
| Host | Localhost binding address |
| Port | 8000 |
| Reload Flag | Enabled for development mode to auto-restart on file changes |
| Worker Count | Single worker sufficient for local development |

## Frontend Deployment

### Package Installation

Node.js dependencies must be installed using the project's designated package manager. The lockfile must be respected to ensure reproducible installations across environments.

### Development Server Startup

The Next.js frontend must be started in development mode with the following configuration:

| Parameter | Value |
|---|---|
| Port | 3000 |
| Hot Reloading | Enabled by default in development mode |

## System Dependencies Verification

Before launching the application, the following external binaries must be verified as available on the system PATH:

| Dependency | Verification Method | Failure Action |
|---|---|---|
| ExifTool | Execute version flag command and check for successful exit code | Display installation instructions and halt startup |
| Tesseract OCR | Execute version flag command and check for successful exit code | Display installation instructions and halt startup |

## Environment Variables

| Variable Name | Purpose | Storage Location |
|---|---|---|
| GEMINI_API_KEY | Authentication for Gemini AI semantic analysis | Exported in shell session or loaded from local environment file |

The API key must never be hardcoded in source files or committed to version control. It should be exported in the terminal session before starting the backend or loaded from a gitignored environment file.

## Windows Compatibility Constraints

All deployment documentation and startup scripts must account for Windows-specific behaviors:

| Concern | Windows Adaptation |
|---|---|
| Process termination | Use double-slash syntax for taskkill commands when scripting process cleanup |
| Path separators | Ensure startup scripts handle backslash paths correctly |
| Virtual environment activation | Reference the Windows-specific activation script within the virtual environment directory |
| Shell differences | Provide equivalent commands for both PowerShell and Git Bash where they diverge |

## Startup Orchestration

A documented procedure or startup script must exist for launching both the backend and frontend terminals. The procedure should specify:

1. Order of operations (backend first, then frontend)
2. Terminal window arrangement recommendations
3. How to verify both services are running before beginning work
4. Graceful shutdown sequence for both processes

## Health Check Endpoint

The backend must expose a health check endpoint that returns service status information including:

| Health Indicator | Description |
|---|---|
| Server status | Confirms the API process is alive and responding |
| ExifTool availability | Reports whether the binary was found and executed successfully |
| Tesseract availability | Reports whether the binary was found and executed successfully |
| Database connectivity | Confirms the SQLite file is accessible and readable |
| Gemini key presence | Confirms the environment variable is set without exposing its value |

This endpoint allows both automated monitoring and manual verification that the local environment is correctly configured before beginning a production workflow session.