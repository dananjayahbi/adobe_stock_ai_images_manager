# Adobe Stock Verified Requirements

**Purpose:** every threshold in the acceptance/refinement/export code should trace
to a published Adobe rule. This document records those rules, their source pages,
and exactly which constant or module enforces each one.

**Verified:** 2026-09-19, against `helpx.adobe.com/stock/contributor/*`.

---

## 1. Photo technical requirements

Source: `submit-photos/technical-legal-requirements-photo-submission.html`,
`submit-to-premium-collection/technical-requirements-premium-collection-submission.html`

| Adobe rule | Enforced by |
|---|---|
| Resolution 4MP–100MP | `config.ADOBE_MIN_MEGAPIXELS` / `ADOBE_MAX_MEGAPIXELS`, `AcceptanceConfig.min_megapixels` / `max_megapixels` |
| File size max 45 MB | `config.ABSOLUTE_MAX_FILE_SIZE_MB`, `AcceptanceConfig.max_file_size_mb` |
| Format: JPEG | `WRONG_FORMAT` issue, `_container_stats.is_jpeg` |
| **sRGB colour profile** | `services/srgb_profile.py` embeds it on export; `has_icc_profile` metric + `NOT_SRGB` issue detect its absence |
| Free of watermarks, timestamps, branding | Stage 2 OCR (`services/ocr_scanner.py`) + semantic audit |
| Quality: "Sharp focus and well-lit" | `_score_detail` (Laplacian variance) + `_score_exposure` |

**Design note — measurement resolution.** Adobe instructs contributors to
*"check images at 100% zoom to identify softness"*. Sharpness and noise are
therefore measured on a **native 1:1 crop**, never on a downscaled proxy:
downscaling averages away exactly the high-frequency signal being measured.
`pixel_metrics._load_native_crop` decodes then crops without resampling.

---

## 2. CSV export limits

Source: `manage-your-portfolio/csv-requirements-content.html`,
`manage-your-portfolio/create-csv-file.html`

| Field | Adobe limit | Enforced by |
|---|---|---|
| Maximum rows | **5,000** | `csv_export.MAX_ROWS` |
| Maximum file size | **1 MB** | `csv_export.MAX_FILE_SIZE_BYTES` |
| Filename | **30 characters max** | `upload_table.MAX_FILENAME_LENGTH` |
| Title | **70 characters max** | `csv_export.MAX_TITLE_LENGTH` |
| Title format | plain text, **no commas or special characters** | `csv_export.sanitize_title` |
| Keywords | 50 (CSV page) / **49** (portal + tips page) | `csv_export.MAX_KEYWORDS` |
| Character encoding | **UTF-8 required** | `csv_export.encode_csv_bytes` (UTF-8 + BOM for Excel) |
| Releases | 30 characters max | emitted empty; only needed for real people/property |

Required columns: `Filename`, `Keywords`, `Title`. Optional: `Category`, `Releases`.
**There is no Description column in Adobe's CSV** — the description is typed in
the portal, which is why the upload table offers a per-field copy button.

**Why the lower keyword figure.** Adobe's CSV page says 50, but the
titles/keywords page and the Contributor Portal both say 49. 49 satisfies both,
so it is the constant used.

**Why filenames are disambiguated.** Adobe caps filenames at 30 characters, but
this app names files after the generated title. Two long titles that share a
prefix truncate to the same name, and Adobe matches a CSV row to an uploaded
file *by filename* — a collision would silently mis-assign metadata. Every
download/ZIP/CSV path therefore passes the record id as a `disambiguator`, which
is appended only when the slug actually had to be shortened.

---

## 3. Titles and keywords best practice

Source: `content-policies-guidelines/metadata/tips-effective-titles-keywords.html`

| Adobe guidance | Enforced by |
|---|---|
| "Keep it short, ideally under 70 characters" | `TITLE_TARGET = 68` in `gemini_metadata.py` |
| Up to 49 keywords | `gemini_metadata.MAX_KEYWORDS` |
| **"The first 10 positions have the greatest influence on search ranking"** | `KEYWORDS_HIGH_IMPACT`, stated explicitly in `METADATA_PROMPT` |
| "Use each keyword once" | dedup in `gemini_metadata.generate_metadata` + `csv_export.build_row` |
| "Submit content in one language only" | `METADATA_PROMPT` |
| "Use local spelling (color vs. colour)" | `METADATA_PROMPT` |
| "Avoid overly technical or gear-heavy terms" | `METADATA_PROMPT` title rules |
| No artist names, real people, brands, trademarks | `PROHIBITED_TERMS` + `adobe_restrictions.scan_metadata` |

---

## 4. Quality and technical refusal reasons

Source: `content-moderation/quality-technical-standards-reasons-content-refusal.html`

This page is Adobe's actual list of grounds for refusal, and it validates the
scoring dimensions:

| Adobe refusal reason | Corresponding check |
|---|---|
| Soft focus / unintended blur | `SOFT_FOCUS` (Laplacian variance, native crop) |
| **"Color fringing: Remove chromatic aberration to prevent colored halos"** | `CHROMA_FRINGE` (channel-misalignment detection) + `EDGE_HALO` |
| "Avoid creating artifacts and noise caused by over-editing" | `EXCESSIVE_NOISE`; refiner strength caps |
| "Avoid extreme exposure settings… may lead to lighting-related refusals" | `HIGHLIGHTS_CLIPPED` + `SHADOWS_CRUSHED` |
| White balance, contrast, saturation → "subtle, balanced adjustments" | `_score_color`; `MAX_TOTAL_DESATURATION` |
| Composition: leave space for text, level horizons | manual review (not automatable) |
| Sensor dust spots | manual review |

**Chroma-fringe detection note.** The metric flags *channel misalignment*
(`max(|Laplacian(r−g)|, |Laplacian(b−g)|) > 25` on edge pixels), not merely
colourful edges. An earlier implementation flagged any large `r−g` difference,
which false-positived on legitimate saturated edges.

---

## 5. Editing DON'Ts → refiner calibration

Source: `submit-photos/photo-editing-best-practices.html`

| Adobe DON'T | Constraint in `services/refine/recipe.py` |
|---|---|
| "Overprocessing with excessive contrast or HDR filters" | `MAX_CORRECTION_STRENGTH = 0.55` caps every single operation |
| "Refrain from heavy color grading… aim for versatile, true-to-life color" | `MAX_TOTAL_DESATURATION = 0.22` caps cumulative desaturation |
| "Over-editing people… unrealistic skin-smoothing" | skin-band correction capped at 18% |
| "Adding non-natural elements or presets" | grain addition targets only the measured noise deficit |
| DO: "Reducing noise without risking key details" | denoise stays light; aggressive smoothing would recreate the flat look |

The refiner's loop is what makes conservatism safe: several gentle passes can
reach the threshold, whereas a single over-edited frame cannot be un-edited.

---

## 6. Similar content — a top refusal reason

Source: `submit-distinct-content/distinct-content-submission-best-practices.html`

> "Similar content is one of the top reasons we refuse content submitted to
> Adobe Stock."

Adobe counts content as too similar when submissions share:

1. **Subject and composition** — the same subject from slightly different angles.
2. **Creative treatment** — one concept with minor colour/filter variation.
3. **Series submissions** — sequential shots with minimal meaningful difference.
4. **Metadata patterns** — *"Different images tagged with identical titles and
   keywords, suggesting they serve the same customer need."*

Enforced by `services/duplicate_detector.py` + `routers/similarity.py`:

* Patterns 1–3 → perceptual **dhash** Hamming distance.
* Pattern 4 → **token-set Jaccard similarity** on title + keywords. This is the
  pattern a generative pipeline produces most readily: asked for twenty variants
  of one prompt, a model emits twenty near-identical titles.

The scan is **advisory only** — it returns groups and a suggested keep-set
(Adobe advises "your strongest three to five photos per subject, angle, or
pose") because choosing which frame to keep is an editorial decision.

---

## 7. Known restrictions

Source: `content-policies-guidelines/content-policies/known-restrictions.html`

~300 entries covering brands (Nike, Adidas, Apple/Google/Amazon Products,
Disney, Lego, Minecraft, Barbie, Louis Vuitton), landmarks (Eiffel Tower, Burj
Khalifa, Sydney Opera House, Colosseum), architecture copyright (Frank Lloyd
Wright Works, Le Corbusier Buildings), people (Albert Einstein, Celebrities and
Impersonators), slogans (May the Fourth Be with You, I Can't Calm Down), and
symbols (Olympic Symbols, Red Cross, UN Emblem, Military Insignia).

Enforced by `services/adobe_restrictions.py`, which filters generated keywords
and warns when a generated title names a restricted subject.

**Critical caveat — over-matching is the real risk.** Adobe's list also contains
generic entries: *Currency*, *Police Forces*, *Public transportation*, *Postage
Stamps*, *Cryptocurrency*. Matching those literally would flag a large share of
legitimate commercial content, so they are excluded via `GENERIC_EXCLUSIONS`.
Three further entries (`oscar`, `ups`, `peeps`) are matched only in a capitalised
form, because in lower case they are ordinary English words ("she ups her game").
Adobe's own page notes the list is "updated periodically, not all-inclusive".

---

## 8. Generative AI specifics

Source: `submit-photos/generative-ai-content-guidelines.html`,
`submit-photos/photo-editing-best-practices.html`

| Adobe rule | Status |
|---|---|
| Must be **marked as Generative AI during submission** in the Contributor Portal | **Manual step** — cannot be automated; the UI should document it |
| "Anatomically incorrect body features, inconsistent lighting, unrealistic proportions" | covered by the semantic audit prompt |
| "Keep embedded text, signature watermarks, and model inconsistencies out" | Stage 2 OCR + semantic audit |
| No AI-tool names in metadata | `PROHIBITED_TERMS` |
