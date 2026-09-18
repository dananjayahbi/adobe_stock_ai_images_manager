# Cross-Origin and Security Specification

## Purpose

This document defines the CORS configuration and local security constraints for the Adobe Stock AI Image Studio. Since the application runs exclusively on a developer workstation, security measures focus on preventing accidental exposure rather than defending against hostile network actors.

## Status

PENDING

## CORS Configuration

The FastAPI backend must implement Cross-Origin Resource Sharing restrictions that permit only the local frontend development server to communicate with the API.

### Allowed Origins

| Origin | Justification |
|---|---|
| http://localhost:3000 | Next.js development server default port |

No other origins should be permitted. Wildcard origin configurations are explicitly forbidden.

### Allowed HTTP Methods

| Method | Usage |
|---|---|
| GET | Fetching records, health checks, retrieving static assets |
| POST | Uploading batches, approving records, triggering mutations |

Only these two methods need to be exposed to the frontend origin. Other HTTP methods should not be included in the allowed methods list unless future endpoints require them.

### Allowed Headers

| Header | Justification |
|---|---|
| Content-Type | Required for multipart uploads and JSON request bodies |
| Authorization | Reserved for potential future token-based flows even though authentication is not currently required |

The CORS middleware must explicitly list these headers rather than using wildcard header permissions.

## Network Binding Constraints

| Constraint | Implementation |
|---|---|
| Backend host binding | Must bind exclusively to localhost loopback address, never to 0.0.0.0 or any network-accessible interface |
| Frontend host binding | Must bind exclusively to localhost loopback address |
| Port assignments | Backend on 8000, Frontend on 3000, both on loopback only |

The application must never be reachable from other machines on the local network. Binding to the loopback interface ensures that only processes on the same machine can establish connections.

## Secret Management

| Secret | Storage Method | Prohibited Actions |
|---|---|---|
| GEMINI_API_KEY | Environment variable exported in shell session or loaded from gitignored file | Never hardcoded in source, never committed to repository, never printed in logs |
| Database credentials | Not applicable (SQLite file-based) | N/A |

Any environment file used for local convenience must be listed in the repository ignore file to prevent accidental commits.

## Version Control Exclusions

The following items must be excluded from version control through the repository ignore file:

| Excluded Item | Reason |
|---|---|
| SQLite database file | Contains runtime state and uploaded record data that is environment-specific |
| Storage directories | Contain uploaded images, generated thumbnails, and staged files that are transient |
| Python virtual environment directory | Platform-specific dependency installation that must be recreated per environment |
| Node modules directory | Downloaded frontend dependencies managed by package lockfile |
| Environment variable files | May contain API keys or local configuration overrides |
| IDE configuration directories | Developer-specific editor settings |

## Authentication Policy

Local endpoints do not require authentication tokens or login flows. The rationale is that the loopback binding constraint already prevents external access, making authentication overhead unnecessary for a single-developer tool. However, CORS configuration remains essential because browsers enforce cross-origin policies even for localhost, and without proper CORS headers the frontend JavaScript would be blocked from making API requests.

## Threat Model Summary

| Threat | Mitigation |
|---|---|
| Accidental network exposure via wrong host binding | Documentation mandates loopback-only binding; health check confirms binding address |
| API key leakage through version control | Environment variables plus repository ignore rules |
| Cross-origin requests from malicious local webpage | Strict CORS origin whitelist limited to port 3000 |
| Database file committed to public repository | Repository ignore exclusion |
| Uploaded images committed to public repository | Storage directory exclusion from version control |

## Operational Verification

During startup, the health check endpoint should report the active CORS configuration status and confirm that the server is bound to the expected loopback address. This provides immediate feedback if the application is accidentally misconfigured to listen on a network-accessible interface.