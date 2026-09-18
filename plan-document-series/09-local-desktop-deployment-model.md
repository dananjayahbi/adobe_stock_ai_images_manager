# 09 — Local Desktop Deployment Model

## Purpose
Choose how the local studio is installed, started, accessed, upgraded, and secured on the target Windows workstation. The model must be simple for a contributor while preserving the browser/backend boundary and managed storage.

## Scope
Deployment options include separate development processes, a browser-local workflow backed by a localhost FastAPI service, LAN access for a trusted device, and a packaged desktop distribution. This document covers process ownership, ports, storage location, startup, upgrades, and recovery. It excludes cloud hosting and public internet deployment.

## Decisions and requirements
The initial MVP should prioritize a localhost deployment: Next.js serves the operator interface and FastAPI provides local APIs, with data stored under an application-controlled workspace. Development may run frontend and backend separately, but the user-facing installation needs one documented startup path and a health check that confirms database, storage, Tesseract, ExifTool, and optional provider readiness.

The backend must bind to localhost by default. LAN exposure is an explicit opt-in with access controls and a warning about images and credentials. The application must not require administrator privileges for ordinary operation if dependencies can be installed in a user-controlled location. Data directories and configuration should be separable so application upgrades do not overwrite user assets.

A packaged desktop shell may be evaluated after the MVP if it materially improves startup and file association. It must not bypass API security or make external tool failures invisible. Upgrade procedures must preserve database migrations, originals, ready files, and configuration backups.

## Affected blueprint areas
This decision affects the Next.js and FastAPI processes, localhost API URL, storage directory tree, environment management, health checks, CORS, installation guide, and operations runbook. It informs documents 07–13, 45–49, 64–66.

## Dependencies
The choice depends on the version matrix, Windows installer strategy, frontend build mode, database migration policy, secret storage, and local-network security requirements. It also depends on whether a durable worker runs in the same process or separately.

## Acceptance criteria
- A fresh Windows user can install and start the application using documented steps.
- Default binding is local-only and the listening port is configurable.
- Startup reports missing tools and unhealthy dependencies clearly.
- Upgrades preserve user assets and apply migrations safely.
- A restart does not lose queued work or corrupt managed files.
- LAN mode, if supported, is opt-in, authenticated or otherwise access-controlled, and documented.

## Risks and open questions
Two-process development can drift from the packaged production behavior. Windows firewall prompts, antivirus scanning, path length limits, and native tool installation may complicate setup. The owner must choose between a script-based distribution and a desktop package, define supported Windows versions, and decide whether the provider credential is stored in an OS secret store or supplied per session.