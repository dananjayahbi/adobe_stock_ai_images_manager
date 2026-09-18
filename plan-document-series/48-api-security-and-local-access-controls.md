# 48 — API Security and Local Access Controls

## Purpose
Protect image content, metadata, credentials, and filesystem boundaries while keeping the desktop application convenient for its intended local operator.

## Scope
Security covers bind address, CORS, browser access, session protection, CSRF, request limits, path exposure, secret handling, logs, and local-network risk. It does not define general threat testing or installation procedures.

## Decisions / requirements
The default backend binds to localhost only. LAN exposure is disabled unless the operator explicitly enables it and accepts a documented warning about authentication, network trust, and image privacy. CORS allows only configured origins; wildcard origins are not used with credentials. Thumbnail and file-serving routes use record identifiers and controlled lookup rather than accepting filesystem paths or arbitrary filenames.

The application establishes a protected local session with a random secret or equivalent mechanism stored outside source control. Mutating browser requests require CSRF protection appropriate to the chosen session design, and cookies use secure settings suitable for local HTTP or documented local TLS. If the MVP uses a single operator token, it must be generated or configured safely, never printed in logs, and rotated without exposing image data.

Upload limits apply at request, batch, file, decoded-pixel, and processing-resource levels. Rate limits and concurrency caps protect provider budgets and local resources. Filenames, metadata, OCR text, provider messages, and error details are treated as untrusted content and escaped or bounded before display and logging. Path traversal, symlink following, extension spoofing, oversized decompression, and arbitrary command execution are explicitly rejected.

Secrets are loaded from environment or protected OS configuration, excluded from diagnostics, and redacted from exceptions. Health endpoints reveal only safe capability state. Logs use correlation identifiers and event categories rather than full image bytes or prompts. A security mode prevents provider upload when external processing is disabled and explains the degraded result.

## Affected blueprint areas
This hardens the FastAPI local service, Next.js origin, upload and thumbnail routes, Gemini credential handling, ExifTool invocation, storage paths, and configuration model.

## Dependencies
It depends on documents 09–13, 21–26, 33, 37, 42, 45–49, and the later security test plan. Windows permissions and firewall behavior require deployment documentation.

## Acceptance criteria
- Localhost is the secure default and LAN exposure is explicit.
- CORS, session, CSRF, and cookie behavior are documented and tested.
- No route accepts arbitrary paths or exposes secrets.
- Resource limits cover uploads, decoding, OCR, provider calls, and exports.
- Logs and diagnostics are bounded and redacted.
- Provider-disabled mode remains safe and understandable.

## Risks / open questions
Localhost services can still be reached by malicious local software or browser-origin tricks. Windows firewall prompts may encourage unsafe exposure. The owner must choose an authentication mechanism, whether TLS is required for LAN mode, and how operators recover a lost local session secret.