# 60 — Security and Abuse Testing

## Purpose
Verify that the local application protects files, credentials, operator actions, and metadata from malformed inputs, unsafe paths, accidental exposure, and realistic local-network abuse.

## Scope
Testing covers upload validation, image parsing, path traversal, symlinks and reparse points, archive and decompression hazards if introduced, API access, browser-origin behavior, secret handling, logs, temporary files, metadata injection, denial-of-service limits, and dependency vulnerabilities. It excludes offensive testing against third-party services.

## Decisions / requirements
The test plan treats all uploaded filenames, content types, metadata strings, OCR text, provider output, and browser inputs as untrusted. Cases include misleading extensions, polyglot or malformed JPEGs, oversized dimensions, truncated files, null bytes, Unicode normalization, traversal segments, duplicate names, links, locked files, and output-directory collisions. The server validates decoded content and resolves paths beneath managed roots; client checks are advisory only.

Security tests confirm credentials never appear in browser payloads, source maps, logs, error envelopes, screenshots, or temporary output. Provider prompts and responses are bounded and sanitized. Generated titles and keywords cannot inject HTML, scripts, control characters, unsafe filenames, or command arguments. ExifTool invocation uses structured arguments and output verification rather than shell interpolation.

Local access controls are tested for localhost binding, allowed browser origins, CSRF-relevant behavior, thumbnail and source authorization, action replay, idempotency misuse, stale revisions, and exposure when another device reaches the port. Rate and size limits protect memory, disk, CPU, OCR, and provider quotas. Error messages are useful without exposing absolute paths, stack traces, secrets, or raw commands.

Testing combines static dependency scanning, secret scanning, focused unit and integration cases, browser abuse scenarios, and manual review of the packaged Windows installation. Findings are classified by exploitability and impact. Critical issues in file handling, credential exposure, arbitrary path access, or unauthorized approval block release.

## Affected blueprint areas
This governs file validation, storage layout, API security, local deployment, configuration, ExifTool and provider adapters, logging, and documents 10, 11, 22, 41, 45–48, and 61.

## Dependencies
It depends on the final binding and origin policy, packaging model, supported Windows permissions, secret storage approach, and any native tools included with the product.

## Acceptance criteria
- Malformed and adversarial uploads fail safely without corrupting managed storage.
- No tested input escapes its intended storage root or becomes a command argument.
- Credentials and sensitive diagnostics are absent from client and logs.
- Unauthorized or replayed actions are rejected consistently.
- Resource limits prevent trivial exhaustion during upload and processing.
- Critical security findings are resolved or explicitly accepted before release.

## Risks / open questions
A local-only product can still be exposed by firewall rules, browser extensions, malware, or shared Windows accounts. The team must decide whether authentication is required beyond loopback, how secrets are stored, and whether a formal penetration test is needed before distributing the installer.