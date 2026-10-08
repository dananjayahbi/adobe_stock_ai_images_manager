# plan.md — Batch Pipeline v2 + new frontend (`frontend-new`)

Date: 2026-10-08 · Status: **complete** (all phases verified — see §8)

## 1. Why

The current UI drives a fixed 7-stage raster pipeline, one stage at a time. We are
replacing it with a **batch-oriented flow**: the operator declares *what kind of batch*
(raster photo vs. transparent-PNG object), picks *which steps run*, optionally saves that
recipe as a **step-profile**, and then runs the **whole pipeline in one go** on a
processing page with a deliberately simple UI. Visual direction: **vintage / aged-paper**
(see reference: parchment surfaces, serif + script type, ink-brown text, brass accents,
ticket-style cards).

The old `frontend/` stays untouched (abandoned, not deleted). `frontend-new/` is the new
Next.js app.

## 2. Product flow

```
Home (/) ─── latest processed images (12 newest)
   ├── [Open gallery]  → /gallery   (all processed images, masonry, lightbox)
   └── [New batch]     → multi-step modal
          Step 1  media type:  Raster photo  |  Transparent PNG
          Step 2  profile:     pick a saved step-profile for that type
                               — or — "Custom pipeline" (skip profile)
          Step 3  steps:       only when Custom — toggle the steps, in canonical order
          ── creates batch (draft) ──
       → /batch/[id]   processing page
             · step cards, each with its config (prefilled from profile if chosen)
             · drag-drop upload zone
             · [Run pipeline] → one background job runs all steps in order
             · live per-step progress + per-image results, cancel button
             · "Save as profile" persists the current step set+configs
```

## 3. Step catalog (single source of truth = `services/pipeline_defs.py`)

Canonical order, key → label, allowed media types, config fields:

| key | label | raster | png | config |
|---|---|---|---|---|
| `bg_remove` | Background removal | – | ✓ | `model` (isnet-general-use / u2net), `edge_check` bool |
| `ocr` | OCR scan | ✓ | ✓ | – |
| `upscale` | Upscale | ✓ | ✓ | `model`, `model_scale`, `target_long_edge`, `gpu_id`, `tta` |
| `refine` | Refine | ✓ | – | `use_semantic` bool |
| `compatibility` | Acceptance QC | ✓ | – | `use_semantic` bool |
| `metadata` | Metadata & keywords | ✓ | ✓ | `delay_seconds` |

Notes:
- PNG batches exclude `refine`/`compatibility`: both are JPEG photo-pipeline concepts
  (refine writes JPEG, the 80% photo gate assumes a rectangular photo). PNG QA is the
  **edge-quality check** that runs inside `bg_remove`.
- Runner sorts picked steps into canonical order before executing.
- `bg_remove` runs first for PNG (OCR then sees only the kept object).

## 4. Backend additions (all additive; old endpoints untouched)

### New tables (`models.py`, created by `create_all`; `batch_id` column in `ADDITIVE_COLUMNS`)
- `batches`: id, name, media_type (`raster|png`), steps JSON `[{key, config}]`,
  profile_id?, status (`draft|running|completed|failed|cancelled`), step_progress JSON,
  error?, created_at, updated_at, finished_at?
- `step_profiles`: id, name, media_type, steps JSON, created_at, updated_at
- `image_records.batch_id VARCHAR(36)` nullable (additive migration)

### New services
- `services/pipeline_defs.py` — the step catalog above + canonical order + validation.
- `services/pipeline_runner.py` — `run_batch(db_factory, batch_id, settings)`:
  iterates the picked steps in canonical order, updates `batch.step_progress`
  (`{key: {status, counts, message}}`) after each step, checks cancel between steps,
  never raises past the task wrapper (marks batch `failed`).
- `services/bg_remover.py` — rembg facade: `remove(path, out_dir, record_id, model)`
  → RGBA PNG at `storage/removed/{id}.png`; lazy model session, default
  `isnet-general-use`.
- `services/edge_quality.py` — alpha edge metrics on the cut-out:
  coverage %, transition-band width (fringe), halo score (edge colour shift vs. core),
  jaggedness (alpha contour oscillation) → `{verdict: pass|warn, scores…}`. Stored in
  `stage_details["bg_remove"]["edge_quality"]`.
- `services/png_ops.py` — alpha utilities: `has_alpha`, `to_white_jpeg` (thumbnail/QC),
  `upscale_rgba` (split alpha → neural/Lanczos upscale of RGB → Lanczos alpha to match →
  merge → PNG), so PNG upscale never routes alpha through the JPEG-writing path.

### New routers
- `routers/batches.py`
  - `GET  /api/batches` — list newest-first (home + gallery badges)
  - `POST /api/batches` — create draft `{name?, media_type, steps, profile_id?}`
  - `GET  /api/batches/{id}` — batch + step_progress + records (with thumbnail URLs)
  - `PATCH /api/batches/{id}` — edit steps/name while draft
  - `DELETE /api/batches/{id}`
  - `POST /api/batches/{id}/files` — multipart upload (raster: PNG→JPEG conversion like
    today; png: keep alpha, `working_path` = inbox original, white-composited thumbnail)
  - `POST /api/batches/{id}/run` — validate + launch `pipeline_runner` as BackgroundTask
  - `POST /api/batches/{id}/cancel` — cooperative cancel between steps
- `routers/step_profiles.py` — `GET/POST /api/step-profiles`, `DELETE /api/step-profiles/{id}`

### Modified (small, surgical)
- `config.py`: add `REMOVED_DIR = STORAGE_ROOT / "removed"`; CORS default already
  covers `:3100` (the new frontend's port). `storage.py:create_data_directories`
  creates `removed/`.
- `services/migrations.py`: append `("image_records", "batch_id", "VARCHAR(36)")`.
- `start-dev.cmd`: CORS list gains `http://localhost:3100` / `127.0.0.1:3100`.
- `requirements.txt`: `rembg` (+ onnxruntime comes transitively).

## 5. Frontend (`frontend-new/`)

Stack pinned like the old app: **Next 14 (App Router) · React 18 · TS · Tailwind 3.4 ·
axios · lucide-react** (`^` ranges only — `>=` pulled Next 16 last time). Port **3100**
(`.env.local`: `PORT=3100`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001`).
`next.config.mjs` (Next 14 can't read `next.config.ts`).

### Design system (vintage, but clean — no skeuomorphic clutter)
- Palette: parchment `#f7f0df/#efe6cf` page, cream `#fbf6ea` panels, ink `#241d12/#3d3222`
  text, brass `#a98541` accents, oxblood `#8b3a2f` primary actions, olive `#5b6334`
  success. Blue-tinted greys are out — everything is warm.
- Type: `Playfair Display` (display), `EB Garamond` (body), `Special Elite`
  (typewriter labels/badges), `Pinyon Script` (logo wordmark).
- Paper grain: SVG feTurbulence data-URI overlay at low opacity + soft vignette.
- Cards: hairline double-frame (border + inset outline), ticket-style dashed dividers,
  small-caps letterspaced button labels, stamp badges (rotated, dashed ring).

### Structure (modular — every component its own file)
```
frontend-new/
  package.json  next.config.mjs  tailwind.config.ts  postcss.config.js  tsconfig.json  .env.local
  src/
    app/
      layout.tsx  globals.css
      page.tsx                 # Home
      gallery/page.tsx
      batch/[id]/page.tsx      # Processing page
    lib/
      client.ts   types.ts   steps.ts        # step catalog mirror + labels/order
      batches.ts  profiles.ts  records.ts
    hooks/
      useBatchPolling.ts  useLatestRecords.ts  useStepProfiles.ts
    components/
      ui/        Button Card Modal Badge ProgressBar Spinner EmptyState Field
      chrome/    Header PaperOverlay Footer Ornament
      home/      LatestGrid ImageCard GalleryCta
      batch/     NewBatchModal (shell) · steps/MediaTypeStep ProfileStep StepsPicker
                 ReviewStep
      gallery/   GalleryGrid GalleryTile Lightbox
      process/   StepList StepCard StepConfig UploadZone RunControls
                 StepProgressBar RecordResultList SaveProfileDialog
```

## 6. Execution order (this session)

1. ✅ Explore codebase
2. ✅ This plan
3. Backend: models/migrations → pipeline_defs → bg_remover + edge_quality + png_ops →
   pipeline_runner → routers → `pip install rembg` → quick pytest of new endpoints
4. Frontend scaffold + npm install
5. Design system + lib/hooks
6. Pages: home → modal → processing → gallery
7. Verify: `tsc --noEmit`, `next build` (never while dev is running), live run against
   the backend, browser check
8. Housekeeping: clear old records/images (keep `storage/app_settings.json` — it holds
   the live LLM key), update `start-dev.cmd`, final status pass over this file

## 7. Decisions (locked, don't relitigate)

- **Ports**: backend 8001, new frontend 3100 (matches `config.py` CORS default).
- **PNG steps**: `bg_remove, ocr, upscale, metadata` only.
- **Raster steps**: `ocr, upscale, refine, compatibility, metadata` (unchanged from today).
- **Profiles are DB rows**, not files (additive tables are free with `create_all`).
- **One background job per batch**, polled through `GET /api/batches/{id}` — the old
  per-stage job registry is untouched.
- **Storage wipe is allowed** (operator has a copy) but `app_settings.json` survives.
- Old `frontend/` code is never edited.

## 8. Status log

- [x] Phase 0 — exploration
- [x] Phase 1 — plan.md
- [x] Phase 2 — backend (models, pipeline_defs, bg_remover, edge_quality,
      png_ops, pipeline_runner, batches + step_profiles routers, rembg installed)
- [x] Phase 3 — scaffold (Next 14, port 3100, pinned `^` deps)
- [x] Phase 4 — design system (parchment/ink/brass/oxblood tokens, Playfair +
      EB Garamond + Special Elite + Pinyon Script, grain + vignette, frame-card)
- [x] Phase 5 — home (hero, latest-processed grid, New batch + Gallery CTAs)
- [x] Phase 6 — modal (type → profile → steps wizard; profile skips the picker)
- [x] Phase 7 — processing page (step cards + config forms, upload zone,
      run/cancel, live per-step polling, save-as-profile)
- [x] Phase 8 — gallery (masonry, search, keyboard lightbox)
- [x] Phase 9 — verification + housekeeping

### Verification evidence (2026-10-08)
- Backend: full pytest suite green (incl. 36 new tests in
  `tests/test_batch_pipeline.py` — catalog, CRUD, upload, run preconditions,
  profiles, runner order/failure/cancel, recovery, edge-quality ground truth).
- Frontend: `npx tsc --noEmit` clean; `next build` succeeds (all 4 routes).
- Live E2E: created a PNG batch → uploaded a synthetic object → ran
  `bg_remove + metadata` → RGBA cut-out written (alpha 0–255), edge verdict
  `pass`, 49 keywords, stage `METADATA_READY`; wizard, processing page,
  gallery lightbox and home grid all exercised in a real browser.
- `start-dev.cmd` now launches `frontend-new` on 3100 (old `frontend/` kept,
  untouched). `storage/` was **not** wiped — existing records display fine in
  the new UI; clearing remains an optional manual step.
