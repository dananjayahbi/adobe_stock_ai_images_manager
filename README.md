# Adobe Stock AI Image Studio

A local desktop application for managing, auditing, and preparing AI-generated images for Adobe Stock submission. Uses a Python FastAPI backend with automated quality control and a Next.js frontend dashboard.

## Universal Platform Foundation (2026-10)

The app is now the foundation of a **universal, multi-platform image-upload studio**: after login you land on a master platform picker, with Adobe Stock fully wired as the first platform and five more marketplaces registered behind "Coming Soon" pages — all sharing one backend, one design system, and the shared upscale/QC/metadata processing layer, while keeping completely isolated storage and databases per platform.

**Route map:** `/login` → `/` (platform picker) → `/adobe-stock/*` (live pipeline) plus `/freepik`, `/vecteezy`, `/dreamstime`, `/123rf`, `/wirestock` (coming soon).

**Auth quick-start:** sign in with `admin` / `admin` (defaults), configured in `.env` via `AUTH_ENABLED`, `AUTH_USERNAME`, `AUTH_PASSWORD`, `AUTH_SECRET_KEY`, and `AUTH_SESSION_TTL_HOURS` (see `backend/.env.example`). Browse on **localhost** — the `studio_session` session cookie is host-scoped, so reaching the app through a different hostname or LAN IP drops the session. This is deliberately lightweight local-first auth, not production-hardened.

**Storage layout:**

```text
storage/
  app_settings.json             # shared, app-level settings
  platforms/adobe_stock/        # Adobe data: 10 data dirs + adobe_stock.db (161 records migrated)
  platforms/<id>/               # one isolated root per future platform (created lazily)
  _recovery_backup/             # one-time migration recovery snapshot
```

System design, isolation rules, and the step-by-step add-a-platform checklist live in [ARCHITECTURE.md](ARCHITECTURE.md).

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
| `GET` | `/api/research/settings` | Prompt Research vocabulary: modes, the default style instruction, the house rules, and the confidence disclaimer. |
| `GET` | `/api/research/runs` | List research threads, newest first. |
| `POST` | `/api/research/runs` | Start a thread and run the first turn. `stream_first: true` creates it without running, so the caller can stream. |
| `GET` | `/api/research/runs/{id}` | One thread, with its stored transcript for replay. |
| `POST` | `/api/research/runs/{id}/messages` | Continue a thread (buffered). The confidence buttons post here. |
| `GET` | `/api/research/runs/{id}/stream` | Continue a thread, streamed as Server-Sent Events. |
| `POST` | `/api/research/runs/{id}/accept` | Push accepted prompts into the Prompt Library as drafts. |
| `DELETE` | `/api/research/runs/{id}` | Delete a thread; prompts already accepted are kept. |
| `GET` | `/api/research/sources` | The uploaded priority-source list. |
| `POST` | `/api/research/sources` | Upload a priority-source file (the raw text, validated server-side). |
| `DELETE` | `/api/research/sources` | Remove it, returning research to general search only. |
| `GET` | `/api/research/sources/template` | Download the exact JSON format as a file. |
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
| `/research` | Prompt Research: an agentic chat workspace that researches a niche and writes generation prompts. |
| `/upload-table` | Copy/paste-ready title/description/keyword rows with image previews, opened in a new tab from the gallery. |

## Prompt Research

Reachable from the header on every route. It sits *before* Stage 1: the prompts it
produces are what the Collector's Prompt Library holds and what the images are
generated from.

| Mode | What it does |
| --- | --- |
| **Static** | A hint in, a fully specified prompt out. No web research. |
| **Batch** | A niche plus a count in, a set of prompts out — each describing a different image, with overlaps flagged before you save. |
| **Research** | The agent searches the web, checks how crowded the niche is, then writes researched prompts. |
| **Find ideas** | The agent proposes niches for you to choose from. It writes no prompts until you pick one. |

The agent is a small tool-using loop, not a single prompt:

| Tool | Purpose |
| --- | --- |
| `web_search` | General web search. |
| `fetch_page` | Read one page in full. |
| `market_overview` | How heavily a niche is already supplied — marketplace share and the catalogue figure printed on a marketplace page. |
| `check_restrictions` | Screen wording against Adobe's known-restrictions list. |
| `check_prompt_similarity` | Flag drafted prompts too alike to be worth generating separately. |
| `assess_validity` | Record the confidence scores **and the idea they describe**; the collective average is computed. |
| `list_categories` | Adobe Stock category codes. |

### The validity check

When it is on, the agent researches the idea, records a scorecard, and **stops** —
offering *Continue with these confidence rates* or *Research a better idea or
niche*. Both buttons send an ordinary chat message, so a button press and a typed
sentence take exactly the same path.

Four things are deliberate:

* **The gate suppresses prompt generation — until you release it.** Asking for
  prompts while also asking the agent to stop and await a decision is a
  contradiction; the model resolves it badly. With the gate on there is no
  output-format block and no similarity tool, because nothing has been drafted yet.
  Pressing *Continue* is what releases it: the agent recognises that message
  (`prompts.is_release_message`) and switches to the JSON prompt contract. Without
  that release the gate was **one-way** — the operator's decision to proceed could
  never turn prompts back on, so Continue produced a second assessment instead of
  the prompts. That was the reported *"the agent didn't provide the prompt at the
  end"*.
* **The scorecard names the idea it assessed.** `assess_validity` requires a
  `subject`, and the card renders it above the numbers. Without it, a *"research a
  better idea"* turn showed three scores and a rationale with no statement of
  *which* idea they were about — the operator could not tell the replacement from
  the idea they had just rejected.
* **The agent keeps looking until the idea clears 80%.** Finding a better idea is
  the whole point of asking for one, so a below-target score is not an answer. The
  prompt says so, but a prompt is a request, not a guarantee: measured live, a run
  researched a replacement and returned **53%** — below the 72% of the idea the
  operator had just rejected — and presented it as the answer. The loop now
  compares the score to `validity.TARGET_AVERAGE` and sends the agent back for a
  different candidate, bounded by `MAX_TARGET_ATTEMPTS`. The tool's own reply
  states the shortfall, so the model sees it too. Nothing is *hidden*: if no
  candidate reaches the target the run reports the best it found with its real
  score.
* **The scores are labelled as a judgement, not a measurement.** Nothing in this
  app has access to keyword volume, download counts or sales data, and search
  results show what *already exists* rather than how many customers would buy it.
  The disclaimer is rendered with the scorecard, not hidden in a tooltip.

### Priority sources

The general search is a fallback chain, and a chain fails as a unit: when the
primary provider is rate-limited or serves an anti-bot page the agent gets
editorial coverage instead of catalogue pages. Measured live, a research run
returned Google News articles for *every* query and reported "0 of 16 stock
marketplaces" — which reads as an empty market but is really a search that never
reached one.

The **Priority sources** section (collapsed by default, above the composer) lets
the operator upload a JSON list of sites that carry the evidence:

```json
{
  "version": 1,
  "sources": [
    {
      "url": "https://stock.adobe.com/search",
      "name": "Adobe Stock search",
      "priority": 1,
      "notes": "The results header shows the catalogue count.",
      "tags": ["marketplace", "catalogue"]
    }
  ]
}
```

Every field but `url` is optional, and a bare list of URLs is also valid — a format
that rejects the operator's first instinct is a format they will not use. **Download
template** gives the exact file, and the template is uploadable *unchanged*, which
is what makes it a specification rather than a sketch.

Four decisions worth stating:

* **The file is parsed on the server, never in the client.** The upload sends the
  file's *text*; a client-side parse would turn a format error into a silent no-op
  that looks like a successful upload.
* **A bad file is refused with the reason, and never replaces a working list.**
  Validation happens before anything is written, so a mistake cannot wipe a list
  the operator spent time on.
* **The section states behaviour, not just a list of sites.** Naming the hosts is
  not enough — the agent's default behaviour (search, read the snippets, answer) is
  exactly what misses them. It is told to restrict its query with the `site:`
  operator, to open a listed page with `fetch_page` rather than trust a snippet
  (catalogue counts live on the page), and that **an unreachable source is not an
  empty one**.
* **Only `http`/`https` URLs are accepted.** They are handed to the fetch tool, so
  the scheme allow-list is a security boundary rather than a formatting preference.

### The JSON output contract

Every prompt-producing run answers in **one JSON object**, not prose with
headings:

```json
{
  "summary": "one sentence describing what was produced",
  "prompts": [
    {
      "title": "short human label",
      "body": "the full generation prompt paragraph, ending with the House Standard's aspect token (e.g. --ar 1:1)",
      "tags": ["2-4 short topical tags"],
      "category": 1,
      "notes": "optional one-line note for the operator"
    }
  ]
}
```

A schema rather than a delimiter, for three reasons:

* **The fields arrive labelled.** The title, tags and category no longer have to
  be inferred from prose, and they are carried all the way into the Prompt
  Library when the prompt is accepted.
* **`json.dumps` escapes newlines.** The payload survives a stored transcript and
  an SSE frame without a second parsing convention.
* **A missing field is a missing key** rather than a silently truncated
  paragraph.

The parser reads the object by **brace matching**, not a regex, because `{` is
legitimate prompt text. A ```json fence, prose around the object, or a bare
string entry are all tolerated; an invented category code is dropped *and*
reported, because Adobe's CSV import rejects a code it does not know. If the
model ignores the contract entirely, the parser falls back to the older delimited
and paragraph paths — and **announces the fallback**, so a guess is never
presented as structured output.

Because the answer is a machine payload, the run stores a **rendered** version of
it (the summary plus the prompt bodies) rather than the raw JSON, and the live
transcript shows the reasoning and tool steps streaming while the payload itself
arrives as parsed cards.

The contract is enforced on the way back too. Protocol markup is **never**
streamed into the transcript, in any mode: a turn's content stops being streamed
the moment it reveals itself to be a tool call, with a short hold-back so a marker
split across two deltas cannot leak its first half. That check is mode-independent
because the validity gate makes `wants_prompts` false, and an earlier version tied
the streaming decision to that flag — so the flagship mode streamed its raw
`<tool_call>{…` markup as the agent's answer.

**A prompt-mode run cannot finish empty.** The instructions state that the answer
is parsed and that a reply in the wrong shape is discarded, and if a run still
answers in prose the agent is told nothing could be read and asked to resend — up
to twice, then its prose is accepted. Without that guard a research run could
write a perfectly readable summary, parse to zero prompts, and be reported as a
clean success: a run that visibly did work and delivered nothing.

### Tool calls: written so they cannot go wrong

The gateway has no native tool calling, so the model *writes* each call as text and
a wrong argument name makes it unusable. Three defences, in order:

1. **The instruction block states the protocol precisely** — exact `name`, exact
   argument names, no nesting, real values (never `""`, `null`, `"value"` or a
   placeholder), one tool per turn, and the call in its own turn with no prose
   beside it.
2. **Every tool is listed with a literal call template**, built from the registry
   so it cannot drift from the tool it describes. A model copies a shape far more
   reliably than it assembles one from a list of parameter names.
3. **Arguments are validated before the tool runs.** A missing or blank required
   argument is rejected with a correction that names it, shows the exact JSON to
   resend, and states that the message is not evidence about the subject — and the
   rejected call is **not** charged to the budget, so a retry cannot burn a run.
   Measured live before this: a `market_overview` call arrived with an empty
   `niche`, the tool answered "No niche given", and the turn was spent.

**The parser is tolerant of how the model *closes* the call, because it does not
reliably use the shape it was asked for.** Captured live from `deepseek-v4.1-flash`,
a call arrives like this:

```text
<tool_call>{"name": "market_overview", "arguments": {"niche": "…"}}</｜｜DSML｜｜ parameter>
```

The JSON is **complete and valid**; only the closing tag is wrong — the model
switches to its native DSML markup mid-envelope. A parser keyed on `</tool_call>`
reads that turn as a final answer, so the call is never executed and the run ends
with nothing to show. That is the operator's *"the agent suddenly stops without
providing the prompts"*, and it is a parser fault, not a model fault: the arguments
were all there. Three consequences are handled explicitly:

* **Envelope scanning is boundary-based.** The body ends at whichever comes first:
  a proper `</tool_call>`, any DSML tag, or the next `<tool_call>` opener. The JSON
  is located by **brace counting**, so a brace or quote inside a query string cannot
  truncate the arguments.
* **A DSML call that nests its arguments under one `arguments` parameter is
  unwrapped**, otherwise a correct call arrives as `{"arguments": {"query": …}}` —
  with no `query` of its own — and is rejected as malformed.
* **A malformed call is not an empty reply.** They get separate counters
  (`MAX_MALFORMED_REPLIES` / `MAX_EMPTY_REPLIES`) and separate corrections. Counting
  the first as the second ended a live run after two hybrids — with four good tool
  results already gathered — under the message "the model stopped producing usable
  output", which was not what had happened.

The same tolerance applies to stripping: a `</tool_call>`-keyed stripper leaves the
*malformed* envelopes in the prose, which is exactly the text that then reaches the
transcript as the agent's own words.

### Long conversations: folding and the context indicator

A research thread grows with every tool call, and a tool result can be thousands
of characters of page text. When it outgrows the window the provider truncates the
request **from the front**, which removes the system prompt and leaves the model
with no instructions — which is what a run "stopping for no reason" looks like.

`services/research/context.py` measures the conversation and folds it before that
can happen, in **two places**, because a conversation can outgrow the window in two
different ways:

| When it folds | What it fits |
| --- | --- |
| At the start of a run | the **stored** history of the thread (`summarise_history`) |
| After each tool round | the **running** conversation of this turn (`compact_live_messages`) |

The second one matters more than it looks. A single turn can add many large tool
results, so a run that began comfortably inside the window can push *itself* out of
it. Measured live with a 4k window before this was wired: the final report sat at
**100% of the window** — the next request would have been truncated, losing the
system prompt. With in-run compaction the same probe finishes at 84.5%.

| Decision | Where it comes from |
| --- | --- |
| When to fold | 70% of the window (`COMPACT_AT_SHARE`) |
| How much room folding must leave | 25% (`DIGEST_RESERVE_SHARE`) |
| What survives verbatim | the **most recent 5 turns** (`KEEP_RECENT_TURNS`) |
| What is folded | everything older, into one digest |
| When the bar warns | 85% of the window (`WARN_AT_SHARE`) |

Six things are deliberate:

* **The recent turns are never paraphrased.** They are what a follow-up refers to
  ("that second idea", "yes, continue"), and a summary of the idea you were just
  given is exactly what makes a follow-up ambiguous.
* **Folding leaves room for the digest.** Folding down to *exactly* the threshold is
  not enough: the digest is spliced into the same request as the turns that are
  kept, so a conversation folded to the threshold still overflows once the digest is
  added. The reserve is what makes the measured percentage actually come *down*.
* **Five turns is a target, not a guarantee.** A tool result can be the whole text of
  a web page, so five of them can exceed a small window on their own — and keeping
  all five would leave the conversation exactly as full as before folding. The
  retention walks down from the newest turn until the kept turns fit, always keeping
  at least one, because a digest with no verbatim anchor cannot be acted on.
* **The system prompt and the current question are pinned.** The first carries the
  instructions, the second is what the run is answering. Neither is ever folded, in
  either place.
* **Folding cannot fail.** If the summariser is unreachable the digest falls back
  to a bounded local excerpt, and either way the operator is told. A silent failure
  here would leave the request overflowing — the very thing being fixed.
* **The digest must preserve figures.** It is instructed to keep every catalogue
  count, marketplace name, blocked search and operator decision, and is told not
  to add advice of its own. Verified live against the gateway: a real conversation
  folded into 729 characters that kept the catalogue figure, the 16/17 marketplace
  share, the blocked fetch and the operator's "no pills" constraint.

The **context bar** above the composer is fed by a `context` event the agent emits
when the run starts, again whenever it compacts mid-run, and again when it finishes,
so the indicator describes the request that was actually sent. It reports the system
prompt separately from the conversation, because that is the part the operator never
sees and cannot trim — knowing it costs a tenth of the window explains why a
short-looking thread is already full. Thresholds come from the backend, so the bar
cannot promise room the backend is about to compact away.

### Watching a run

A research turn can legitimately take a minute, so a bare spinner is not enough.
The transcript shows the model's reasoning (collapsed, and collapsible) and one
row per tool call with its arguments and result as they arrive; the composer
reports what is actually happening — *Thinking…*, *Running web_search — …*,
*Writing the answer…* — derived from the stream rather than from a timer.

Two details are worth knowing if you change this code:

* **The turn being streamed has no assistant message yet.** It is created only
  when the turn finishes, so live activity must render outside the message list.
  Rendering it only inside an assistant message hid the whole first turn.
* **Every turn's activity is kept, not just the last one.** The event stream is a
  single flat list across the conversation, so attributing a tool step to a
  specific turn needs a boundary — and the backend provides one, because every turn
  ends with its own `run_finished`. The reducer segments on that, so each assistant
  message is shown with the reasoning and tool calls that produced it. Attaching
  them only to the last turn meant reopening a finished conversation showed answers
  with no trace of how they were reached.
* **A turn that ends without writing an answer still shows its work.** The
  transcript renders one assistant bubble per stored *message* and attaches the
  n-th turn's activity to it, so a turn with no message has nowhere to attach —
  and the reasoning the operator was reading disappeared the moment the run
  stopped. `orphanedTurn` returns that trailing activity and the transcript renders
  it explicitly, labelled as a turn that ended without an answer. This is why the
  activity is **not** promoted back into the live buffers on `run_finished`: a
  promoted buffer is archived again by the next turn's `run_started`, which showed
  one turn as two.
* **Closing a turn is idempotent, and that matters.** A failed turn emits *both*
  `error` and `run_finished` — the backend's error path yields the error and then
  the terminal event. `closeTurn` returns the live buffers **cleared**, so the
  second close appends nothing. Spreading `...state` instead of the cleared result
  was a real bug: it left the buffers live and the error path archived the same
  reasoning twice.
* **A silent turn is retried, then finalised — not discarded.** A reasoning model
  routinely emits a thinking-only turn, and a run that already gathered evidence
  must not be thrown away because the final phrasing turn misbehaved. If nothing
  usable can be recovered from the transcript, the tools are withheld and the
  model is asked once more for a conclusion, because a run that shows its research
  and then ends in silence is the same defect as a stalled spinner.

Two storage details are worth knowing, because both fail *silently*:

* **`result` is a JSON column.** It must receive plain data. Storing the
  `ValidityView` dataclass that `validity.describe` returns raises
  `TypeError: … not JSON serializable` — and because that happens inside the
  stream's `finally` block, the turn is lost and the conversation stays `RUNNING`
  forever. It only bit the *success* path of the validity gate, because a run with
  no assessment stores `None`, which serialises fine.
* **A persistence failure is recorded, not swallowed.** The run is marked
  `FAILED` with the reason, so the thread shows what happened instead of claiming
  a turn is still running.

### Two search providers, because one is not enough

DuckDuckGo's lite front-end answers a scripted query, but it rate-limits
aggressively — a burst of eight queries got the anti-bot challenge on all eight,
and the block persisted. Google News RSS is tried as a fallback: no key, a stable
documented shape, and dated, attributed articles. A fallback result is **marked as
one** and the tool text says news coverage is not marketplace catalogue data.

A failure is never rendered as an empty result set. If every provider fails, the
model is told explicitly not to conclude that the niche has no competition —
otherwise a blocked search would look like an underserved market.

### How the agent calls tools

The configured gateway does not support OpenAI tool calling (verified: sending
`tools` returns `finish_reason: "stop"`, `tool_calls: null`, and the intended call
leaked into `content` as DeepSeek's internal `DSML` markup). So tool calls are
exchanged as **text** and parsed from three shapes: the requested
`<tool_call>{"name": …, "arguments": {…}}</tool_call>` envelope, fenced JSON, and
the DSML markup. Prose that merely mentions a tool is not read as a call — that
would stop the loop from ever terminating.

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

