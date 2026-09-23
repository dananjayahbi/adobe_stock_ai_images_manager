# Adobe Stock AI Image Studio

A local desktop application for managing, auditing, and preparing AI-generated images for Adobe Stock submission. Uses a Python FastAPI backend with automated quality control and a Next.js frontend dashboard.

## Quick Start

### Prerequisites

| Requirement | Version | Notes |
| --- | --- | --- |
| Python | 3.11+ | 3.11 or 3.12 recommended |
| Node.js | 20+ | Ships with npm |
| ExifTool | 12.70+ | Auto-detected on `PATH` or at `%LOCALAPPDATA%\Programs\ExifTool` |
| Tesseract OCR | 5.3+ | Auto-detected on `PATH` or at `C:\Program Files\Tesseract-OCR` |
| LLM gateway | — | OpenAI-compatible endpoint (see below) |

Install the two native tools with winget (no admin needed for ExifTool):

```powershell
winget install --id OliverBetz.ExifTool --exact
winget install --id UB-Mannheim.TesseractOCR --exact
```

Both are resolved automatically at startup — from `PATH` first, then from their
standard install directories — so a stale `PATH` won't break the pipeline.

### LLM gateway

Semantic QC and metadata generation go through any **OpenAI-compatible**
`/chat/completions` endpoint. The default targets a local multi-provider router
that routes by *virtual model name*:

```env
LLM_BASE_URL=http://localhost:4006/api/gateway/v1
LLM_MODEL=OpenRouter-Free-Endpoint
LLM_API_KEY=<pool gateway key>
LLM_TIMEOUT_SECONDS=240
LLM_IMAGE_MAX_DIM=1024
```

`LLM_IMAGE_MAX_DIM` downscales images before upload, keeping vision requests
small. Any OpenAI-compatible provider works — point `LLM_BASE_URL` at OpenAI,
OpenRouter, Groq, etc. and set `LLM_MODEL` to the model id.

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # Windows (cp on macOS / Linux)
# then edit .env and set LLM_API_KEY
python -m uvicorn main:app --reload --port 8000
```

> `config.py` loads `.env` from either the repo root or `backend/` (the latter
> wins), so running the command above from `backend/` works as-is.

The API is then available at http://localhost:8000, with interactive docs at
http://localhost:8000/docs.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 in your browser.

### Tests

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q
```

## API Reference

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/upload` | Upload a batch of JPEGs (multipart field `files`, max 50). |
| `GET` | `/api/records` | List records, newest first. Filters: `status`, `used` (`all`/`used`/`unused`), `queued`, `prompt_id`, `stage` (comma-separated pipeline stages), `search` (substring across title/description/keywords/filenames/category), `ids` (comma-separated), `limit` (≤500), `offset`. |
| `GET` | `/api/records/{id}` | Fetch a single record. |
| `POST` | `/api/records/{id}/approve` | Approve a record, optionally overriding title/description/keywords. |
| `PATCH` | `/api/records/{id}/used` | Mark one record as used/unused (`{"is_used": true}`). |
| `PATCH` | `/api/records/used` | Mark many records as used/unused (`{"record_ids": [...], "is_used": true}`). |
| `DELETE` | `/api/records/{id}` | Delete a record and all of its on-disk artifacts. |
| `POST` | `/api/records/bulk-delete` | Delete many records (`{"record_ids": [...]}`). |
| `GET` | `/api/records/{id}/download` | Download the staged, metadata-tagged file (READY only). |
| `POST` | `/api/records/download-zip` | ZIP archive of staged files (max 50 per request). |
| `POST` | `/api/upload-table` | Build copy/paste metadata rows for the selected records. |
| `POST` | `/api/assets/rename` | Set the Adobe upload filename for one or more records (blank clears the override). |
| `POST` | `/api/assets/rename-suggest` | Propose filenames derived from the generated titles, without writing. |
| `POST` | `/api/assets/apply-suggested-names` | Adopt the metadata model's proposed filenames (falls back to the title). |
| `POST` | `/api/assets/force-accept` | Force records past the acceptance gate, recording the reason. |
| `POST` | `/api/assets/csv` | Download the Adobe Stock CSV for a selection (`only_ready` defaults true). |
| `POST` | `/api/assets/csv/preview` | CSV text plus warnings, without downloading. |
| `POST` | `/api/assets/bundle` | ZIP the selected images **and** their CSV together. |
| `GET` | `/api/prompts` | List generation prompts. Filters: `status` (`all`/`used`/`unused`/`bound`/`unbound`/`archived`, alias `draft`). |
| `POST` | `/api/prompts` | Create a prompt (title derived from the body when blank). |
| `GET` | `/api/prompts/{id}` | Fetch one prompt with its binding count. |
| `PATCH` | `/api/prompts/{id}` | Partial update; also marks a prompt used/draft/archived by hand. |
| `DELETE` | `/api/prompts/{id}` | Delete a prompt, keeping and unbinding its images. |
| `POST` | `/api/prompts/{id}/bind` | Bind images to a prompt, or unbind (`{"record_ids": [...], "unbind": true}`). |
| `GET` | `/thumbnails/{filename}` | Static thumbnail images. |
| `GET` | `/health` | Liveness probe. |

### Prompt filters: two independent axes
A prompt's *consumed* state and its *binding* state are different things — a
prompt can be used elsewhere without anything being collected here. The list
endpoint reports both, and they legitimately disagree:

| Axis | Filters | Reads |
| --- | --- | --- |
| Status | `used`, `unused`, `archived` | `Prompt.status` |
| Binding | `bound`, `unbound` | live count of linked `image_records` |

`unused` is the status twin of `used` (still a draft); "no image bound" is
`unbound`. `GET /api/prompts` returns `used`/`unused`/`archived` **and**
`bound`/`unbound` as separate totals, so they must not be summed.

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Pipeline dashboard: upload, live QC status, batch approve. |
| `/gallery` | Masonry gallery of staged assets — usage filters, multi-select, ZIP download, bulk delete, and "Generate upload table". |
| `/upload-table` | Copy/paste-ready title/description/keyword rows with image previews, opened in a new tab from the gallery. |

## Delivery: filenames, forced acceptance, CSV & ZIP

From **Metadata & CSV** onward the job changes from *processing* images to
*delivering* them, so the same three controls follow the record wherever it sits
— including the Gallery's published view:

| Control | Why it exists |
| --- | --- |
| **Use suggested names** | The metadata model names each asset while looking at it, so its proposal is usually better than a truncated title. One click applies it to the selection. |
| **Filenames** | Adobe matches each CSV row to an uploaded file **by filename**. Names are normalised to Adobe's rules (lower-case, hyphens, JPEG, ≤30 chars), and can be reviewed or rebuilt in bulk from the generated titles. |
| **Force accept** | The acceptance gate is a heuristic and the score is a *ranking* signal. The operator can override it; the **score and the scorer's issues are preserved** and the override is recorded with a reason, so it is never mistaken for a pass. |
| **CSV / ZIP + CSV** | Generated from the *current selection*. The ZIP contains the images **and** the CSV that names them, so the two cannot drift apart. |

Two rules the code enforces rather than trusting:

- **One name, everywhere.** `ImageRecord.upload_filename` is the single source of
  truth, read by the CSV, the ZIP entry, the download and the UI. `download_name`
  stores the name that will be used; when unset the name is derived from the
  title. `suggested_filename` holds the model's **proposal** and is never the
  delivered name until the operator applies it.
- **A name is derived from the title alone.** No record id, hash, or code is ever
  mixed into it — the filename is a deliverable the operator reads and uploads,
  not an internal key. Batch uniqueness is applied where the batch is known: a
  colliding row gets a readable `-2`, and its title is re-shortened so the marker
  fits rather than clipping an already-full name mid-word.
- **A CSV row must name a file that is actually delivered.** The bundle builds its
  CSV from the *staged* records, so an unpublished selection cannot produce a row
  for a file that is not in the archive. Because publishing is what stages that
  file, **Metadata & CSV offers the CSV but not the bundle** — the bundle appears
  on the Gallery, where the staged assets are.
- **Publishing stages the pipeline's quality copy** (`working_path` — the
  refined/upscaled output), falling back to the inbox original only when no
  working copy exists. Staging the raw upload would silently discard every
  stage's work.
- **Metadata generation is allowed below the threshold.** Only an `OCR_REJECTED`
  record is blocked, because embedded text is a content-policy violation rather
  than a quality judgement.

## Published gallery

The published gallery (`/gallery`) is the endpoint of the pipeline, so it is
reachable from the header on every route as well as from Stage 7.

| Filter | Reads | Notes |
| --- | --- | --- |
| **Search** | title, description, keywords, `filename`, `download_name`, `suggested_filename`, category | Debounced; matches a keyword that never made it into the title, and the delivered filename. |
| **Usage** | `is_used` | `unused` / `used` / `all` — independent of the stage scope. |
| **Scope** | `stage` | `Published` (default) or `All stages`. |

Scope is by **stage**, not by the legacy `status` column: `status` is the QC
verdict, so `status=READY` also matched records that were approved but not yet
published. An invalid `stage` value is a **400**, not an empty result — a filter
that silently matches nothing is indistinguishable from a broken one.

## Reported metrics describe the *delivered* file

`width`, `height`, `megapixels` and `file_size_bytes` used to be measured once at
ingestion, on the **inbox original**, and never refreshed. After an upscale the
two disagreed by 8x: a published asset whose delivered file is **3840x2143
(8.2 MP)** reported **1376x768 (1.06 MP)** — which reads as "publishing shrank my
image".

That was not cosmetic either: `low_resolution` is a **critical** acceptance issue
scored from the megapixels, so a stale 1.06 MP claimed a below-Adobe-floor
resolution for an asset that passes comfortably.

`services/record_metrics.py` owns the measurement, and every place that changes
`working_path` (upload conversion, upscale, refine, autofix) plus publish calls
it, so the reported geometry follows the file. `services/metric_repair.py`
re-measures existing records once at startup — it is self-limiting, so a second
boot does nothing.

## Published gallery

The published gallery (`/gallery`) is the endpoint of the pipeline, so it is
reachable from the header on every route as well as from Stage 7.

| Filter | Reads | Notes |
| --- | --- | --- |
| **Search** | title, description, keywords, `filename`, `download_name`, `suggested_filename`, category | Debounced; finds a keyword that never made it into the title, and the delivered filename. |
| **Usage** | `is_used` | `unused` / `used` / `all` — independent of the stage scope. |
| **Scope** | `stage` | `Published` (default) or `All stages`. |

Scope is by **stage**, not by the legacy `status` column: `status` is the QC
verdict, so `status=READY` also matched records that were approved but not yet
published. An invalid `stage` value is a **400**, not an empty result — a filter
that silently matches nothing is indistinguishable from a broken one.

## Reported metrics describe the *delivered* file

`width`, `height`, `megapixels` and `file_size_bytes` used to be measured once at
ingestion, on the **inbox original**, and never refreshed. After an upscale the
two disagreed by 8x: a published asset whose delivered file is **3840×2143
(8.2 MP)** reported **1376×768 (1.06 MP)** — which reads as "publishing shrank my
image".

That was not cosmetic either: `low_resolution` is a **critical** acceptance issue
scored from the megapixels, so a stale 1.06 MP claimed a below-Adobe-floor
resolution for an asset that passes comfortably.

`services/record_metrics.py` owns the measurement, and every place that changes
`working_path` (upload conversion, upscale, refine, autofix) plus publish calls
it, so the reported geometry follows the file. `services/metric_repair.py`
re-measures existing records once at startup — it is self-limiting, so a second
boot does nothing.

## Pipeline

Each upload enters a state machine and is processed by a background task:

```mermaid
stateDiagram-v2
    [*] --> PENDING: upload
    PENDING --> AUDITING: background task starts
    AUDITING --> PASSED: all QC checks + semantic score ≥ 0.75
    AUDITING --> FLAGGED: any check fails
    PASSED --> APPROVED: approve (or batch approve)
    FLAGGED --> APPROVED: manual override & approve
    APPROVED --> READY: ExifTool metadata embedded, copied to ready_to_upload
```

Deterministic QC runs first (resolution, Laplacian-variance sharpness, colour
space, Tesseract OCR), then the LLM performs semantic QC and generates title,
description and keywords. Approval writes IPTC/XMP metadata with ExifTool and
copies the file into the ready-to-upload directory.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite (WAL mode)
- **Frontend**: Next.js App Router + Tailwind CSS + Axios
- **AI**: OpenAI-compatible LLM gateway (vision + JSON mode) for semantic QC and metadata
- **QC**: OpenCV (sharpness), Pillow (resolution/color), Tesseract (OCR)

## Project Layout

| Path | Purpose |
| --- | --- |
| `backend/config.py` | Pydantic settings and all QC thresholds. |
| `backend/database.py` | SQLAlchemy engine, session factory, WAL pragmas. |
| `backend/models.py` | `ImageRecord` ORM model and `ImageStatus` enum. |
| `backend/schemas.py` | Pydantic request/response models. |
| `backend/routers/` | `upload`, `records`, `approve`, `gallery` API endpoints. |
| `backend/services/` | `qc_engine`, `llm_client`, `gemini_auditor`, `gemini_metadata`, `exiftool_embedder`, `storage`, `upload_table`, `migrations`. |
| `backend/tasks/` | `audit_orchestrator` background pipeline. |
| `backend/tests/` | Pytest suite (QC engine + API integration). |
| `frontend/src/lib/api.ts` | Typed API client. |
| `frontend/src/lib/clipboard.ts` | Clipboard helper with a non-secure-context fallback. |
| `frontend/src/lib/uploadTableStore.ts` | Cross-tab hand-off of the gallery selection. |
| `frontend/src/components/` | Shared UI: `NavBar`, `Dropzone`, `StatsBar`, `ImageGrid`, `InspectionModal`, `ConfirmDialog`, `CopyButton`. |
| `frontend/src/components/gallery/` | Gallery view, masonry grid, tile, toolbar, preview modal, hooks. |
| `frontend/src/components/uploadTable/` | Upload-table view, table, and row components. |
| `frontend/src/app/page.tsx` | Live polling dashboard. |
| `frontend/src/app/gallery/page.tsx` | Gallery route. |
| `frontend/src/app/upload-table/page.tsx` | Upload-table route. |
| `plan-document-series/` | Design and planning documents. |
| `storage/` | Runtime data: `inbox/`, `thumbnails/`, `ready_to_upload/`, SQLite DB. |

