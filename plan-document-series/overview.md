# Plan Document Series Overview

This directory contains the decomposed plan document series for the **Adobe Stock AI Image Studio** project. Each document is a focused micro-specification designed to be consumed independently by AI agents during implementation.

> **Rule:** No code snippets are included in any plan document. Each document describes purpose, responsibilities, interfaces, constraints, and behavior only.

---

## Document Index (35 Documents)

### Foundation & Architecture
| # | Filename | Description |
|---|----------|-------------|
| 01 | `project-vision-and-scope.md` | Executive summary, goals, non-goals, target users, and success metrics |
| 02 | `system-architecture-overview.md` | High-level component diagram, data flow between frontend, backend, storage, and external APIs |
| 03 | `directory-structure-plan.md` | Complete file tree with purpose annotations for every directory and key file |
| 04 | `tech-stack-and-dependencies.md` | Language versions, frameworks, system binaries, Python packages, npm packages |
| 05 | `data-flow-pipeline.md` | End-to-end lifecycle of an image from upload to ready-to-upload pool |

### Adobe Stock Compliance
| # | Filename | Description |
|---|----------|-------------|
| 06 | `adobe-stock-baselines.md` | Commercial and technical acceptance criteria mapped to enforcement rules |
| 07 | `file-format-constraints.md` | JPEG baseline requirements, color space normalization, file size bounds |
| 08 | `metadata-tagging-rules.md` | IPTC/XMP field mapping, keyword count limits, forbidden terms list |
| 09 | `generative-ai-compliance.md` | Adobe Stock AI disclosure requirements and portal workflow alignment |

### Backend Core
| # | Filename | Description |
|---|----------|-------------|
| 10 | `backend-entry-point.md` | FastAPI ASGI app initialization, middleware, CORS, router mounting |
| 11 | `configuration-management.md` | Environment variables, threshold constants, path resolution strategy |
| 12 | `database-engine-setup.md` | SQLite engine creation, session factory pattern, connection lifecycle |
| 13 | `image-record-model.md` | SQLAlchemy ORM entity fields, state machine transitions, indexes |
| 14 | `pydantic-schemas.md` | Request/response payload contracts for all API endpoints |

### Backend Services
| # | Filename | Description |
|---|----------|-------------|
| 15 | `qc-engine-deterministic.md` | Resolution check, megapixel calculation, color mode validation logic |
| 16 | `qc-engine-laplacian-sharpness.md` | Laplacian variance computation, threshold rationale, grayscale conversion |
| 17 | `qc-engine-ocr-gibberish.md` | Tesseract integration, downscale strategy, gibberish detection heuristic |
| 18 | `gemini-service-semantic-audit.md` | Gemini Flash prompt design for artifact/IP detection, JSON response parsing |
| 19 | `gemini-service-metadata-generation.md` | Title and keyword generation prompt, ordering rules, forbidden tag filtering |
| 20 | `exif-service-iptc-embedding.md` | ExifTool subprocess invocation, IPTC/XMP field mapping, error handling |
| 21 | `thumbnail-generator.md` | Pillow-based thumbnail creation, sizing constraints, output quality |

### Backend API & Orchestration
| # | Filename | Description |
|---|----------|-------------|
| 22 | `api-upload-endpoint.md` | Multipart batch upload handler, file persistence, record creation |
| 23 | `api-records-endpoint.md` | GET endpoint for fetching records with status filtering and pagination |
| 24 | `api-approve-endpoint.md` | Single-record approval flow: metadata gen, file copy, IPTC embed, state update |
| 25 | `background-task-orchestrator.md` | BackgroundTasks dispatch, sequential QC stages, state transitions, error capture |
| 26 | `storage-directory-management.md` | Inbox, thumbnails, and ready-to-upload directory lifecycle and cleanup |

### Frontend Application
| # | Filename | Description |
|---|----------|-------------|
| 27 | `frontend-project-setup.md` | Next.js App Router configuration, Tailwind setup, TypeScript config |
| 28 | `frontend-api-client.md` | Axios/fetch wrapper, base URL configuration, polling interval strategy |
| 29 | `component-dropzone.md` | Drag-and-drop upload component, multipart form construction, callbacks |
| 30 | `component-image-grid.md` | Filterable card grid layout, status-based styling, filter tab bar |
| 31 | `component-inspection-modal.md` | 100% zoom viewer, failure reason display, manual override action |
| 32 | `component-stats-bar.md` | Queue counters, health metrics display, batch approve button |
| 33 | `dashboard-page-layout.md` | Main page composition, state management, polling useEffect, theme |

### Operations & Workflow
| # | Filename | Description |
|---|----------|-------------|
| 34 | `local-development-workflow.md` | Prerequisites, terminal commands, environment startup sequence |
| 35 | `daily-production-protocol.md` | Step-by-step operator workflow from image generation to Adobe Stock submission |

---

## Document Conventions

- **No code snippets.** Documents describe behavior, interfaces, and constraints in natural language and tables only.
- **Modular scope.** Each document covers exactly one component or concern. Cross-references use filename links.
- **Agent-ready.** Documents are self-contained enough for an AI agent to implement the described component without reading the entire series.
- **Consistent terminology.** Status values (`PENDING`, `AUDITING`, `PASSED`, `FLAGGED`, `READY`) are used uniformly across all documents.
