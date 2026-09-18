# 08 — Technology Stack and Version Matrix

## Purpose
Create a controlled compatibility matrix for the runtimes, frameworks, libraries, external tools, and provider SDKs used by the studio. Reproducible versions reduce failures caused by undocumented local environments.

## Scope
The matrix covers Python and FastAPI, SQLAlchemy and SQLite, Pydantic, Pillow, OpenCV, Tesseract, the Gemini SDK, ExifTool, Node.js, Next.js, React, the frontend transport and styling libraries, and supported operating-system assumptions. It does not prescribe exact patch versions until installation testing confirms them.

## Decisions and requirements
The project should select currently supported versions that are compatible with Windows and the chosen packaging model, then pin direct dependencies and record transitive lock data. Python image libraries must agree on supported formats and native dependencies. Tesseract and ExifTool are external prerequisites with independently verified versions and executable discovery rules.

The Gemini client must use a maintained SDK and an adapter so provider changes do not spread into domain code. The frontend and backend API schemas are versioned separately from dependency upgrades. Node and Python versions must be documented for development and release, with one tested baseline. A matrix entry includes version range, selected version, reason, installation source, compatibility notes, and verification date.

Dependency upgrades require targeted unit, integration, fixture, and end-to-end tests. Security advisories and abandoned libraries trigger review. The matrix must distinguish required runtime dependencies from optional development tools and must state whether a package is bundled, installed globally, or discovered on PATH.

## Affected blueprint areas
This plan applies to the blueprint’s requirements file, package manifest, FastAPI/Next.js architecture, Pillow/OpenCV/PyTesseract usage, Gemini integration, ExifTool wrapper, SQLite layer, and Windows setup. It feeds documents 07, 09–10, 32–38, 58–65.

## Dependencies
A final matrix requires choosing a durable worker strategy, deployment packaging, supported Windows versions, frontend styling and HTTP libraries, and the exact Gemini API surface. Native tool installation and license review are also dependencies.

## Acceptance criteria
- Direct dependencies and runtime versions are explicitly pinned or bounded with rationale.
- A clean Windows environment can install the documented stack.
- Tesseract and ExifTool discovery is deterministic and diagnostically reported.
- Dependency upgrades have a reproducible verification procedure.
- Provider and framework APIs are isolated behind stable internal contracts.
- The matrix records verification dates and known incompatibilities.

## Risks and open questions
The blueprint names libraries but does not specify versions, lockfiles, or a packaging mechanism. OpenCV and Tesseract can be difficult to distribute consistently on Windows. Gemini SDK APIs may change faster than the application. The project must decide whether to support only one Python/Node pair, whether to bundle native tools, and how security patches are backported without destabilizing policy-sensitive behavior.