"""Prompt Research endpoints.

The agentic research workspace: chat with a research agent that can search the
web, check how crowded a niche is, score its own confidence, and hand the prompts
it writes straight to the Prompt Library.

Endpoints:

* ``GET    /api/research/settings``            - modes, the default style
  instruction, and the house rules (so the UI hard-codes nothing)
* ``GET    /api/research/runs``                - the conversation list
* ``POST   /api/research/runs``                - start a conversation
* ``GET    /api/research/runs/{id}``           - one conversation, with transcript
* ``POST   /api/research/runs/{id}/messages``  - continue it (non-streaming)
* ``GET    /api/research/runs/{id}/stream``    - continue it, streamed (SSE)
* ``POST   /api/research/runs/{id}/accept``    - push prompts into the library
* ``DELETE /api/research/runs/{id}``           - delete the thread
* ``GET    /api/research/sources``             - the uploaded priority sources
* ``POST   /api/research/sources``             - upload a priority-source file
* ``DELETE /api/research/sources``             - remove it
* ``GET    /api/research/sources/template``    - download the exact JSON format

Why both a buffered and a streaming way to continue a conversation
------------------------------------------------------------------
The operator's experience needs the stream: watching the agent think and open
sites is the feature. But a stream cannot be *tested* or *scripted* conveniently,
and a client with a flaky connection should still be able to complete a turn. So
the same run is exposed twice — ``/messages`` drains it and returns the result,
``/stream`` forwards each event as it happens. Both call the same agent.
"""

from __future__ import annotations

import json
import logging
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

import database
from database import get_db
from models import ResearchRunStatus
from schemas import (
    ResearchAcceptRequest,
    ResearchAcceptResponse,
    ResearchFollowUpRequest,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchRunSummary,
    ResearchSettingsResponse,
)
from services import app_settings
from services.research import (
    agent,
    context as context_module,
    events as event_module,
    inflight,
    prompts,
    runs,
    source_store,
    sources,
    validity,
)
from services.research.agent import DEFAULT_MAX_TOOL_CALLS, RunRequest
from services.research.synthesis import MAX_PROMPTS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["research"])

#: Modes the API accepts, with the copy the UI renders. Defined here rather than
#: in the frontend so a mode cannot be offered without the backend knowing it.
MODES: tuple[dict, ...] = (
    {
        "id": "static",
        "label": "Static",
        "tagline": "Give a hint, get a refined prompt",
        "description": (
            "Describe what you want in a sentence. The agent writes a fully "
            "specified prompt in your house style. No web research."
        ),
        "produces_prompts": True,
        "researches": False,
        "supports_count": True,
        "supports_validity": False,
    },
    {
        "id": "batch",
        "label": "Batch",
        "tagline": "Describe a niche, get a set of prompts",
        "description": (
            "Describe a niche and how many prompts you need. Each prompt "
            "describes a clearly different image, and overlaps are flagged before "
            "you save them."
        ),
        "produces_prompts": True,
        "researches": False,
        "supports_count": True,
        "supports_validity": False,
    },
    {
        "id": "research",
        "label": "Research",
        "tagline": "Investigate a niche, then write prompts",
        "description": (
            "The agent searches the web, checks how crowded the niche is, and "
            "writes researched prompts. With the validity check on, it scores the "
            "idea first and waits for your decision."
        ),
        "produces_prompts": True,
        "researches": True,
        "supports_count": True,
        "supports_validity": True,
    },
    {
        "id": "ideas",
        "label": "Find ideas",
        "tagline": "Ask what is worth pursuing",
        "description": (
            "The agent researches demand and competition, then proposes distinct "
            "niches for you to choose from. It writes no prompts until you pick one."
        ),
        "produces_prompts": False,
        "researches": True,
        "supports_count": False,
        "supports_validity": True,
    },
)

#: Accepted mode ids, for validation.
MODE_IDS = tuple(mode["id"] for mode in MODES)

#: Prompt counts the API accepts. The upper bound matches the synthesis cap so a
#: request cannot ask for more than one answer can carry.
MIN_PROMPT_COUNT = 1

#: Longest accepted operator message.
MAX_MESSAGE_LENGTH = 8_000

#: Headers that stop a proxy from buffering the SSE stream. Without these a
#: reverse proxy collects the whole response and the "live" view arrives at once,
#: which silently defeats the feature.
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def get_session_factory():
    """The session factory the streaming endpoint opens its own sessions from.

    A **dependency**, not a by-name import of ``database.SessionLocal``, for two
    reasons:

    * The streaming body outlives the request's dependencies, so it cannot use the
      injected session; it needs its own.
    * A by-name import would hard-wire it to the real ``storage/adobe_stock.db``,
      so a test client's run would be written to the operator's live database and
      invisible to the test that created it. That is the same defect that once
      made a record created through the test client invisible to its own CSV
      export. Overriding this dependency is how the test suite redirects it.
    """
    return database.SessionLocal


def _get_run_or_404(db: Session, run_id: str):
    run = runs.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Research run {run_id} does not exist.")
    return run


def _validate_mode(mode: str) -> str:
    key = (mode or "").strip().lower()
    if key not in MODE_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode. Accepted values: {', '.join(MODE_IDS)}.",
        )
    return key


def _clamp_count(value: int | None, default: int = 1) -> int:
    """Clamp a requested prompt count into the supported range."""
    try:
        count = int(value) if value is not None else default
    except (TypeError, ValueError):
        return default
    return max(MIN_PROMPT_COUNT, min(MAX_PROMPTS, count))


def _clean_message(message: str) -> str:
    text = (message or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="A message is required.")
    if len(text) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"A message may be at most {MAX_MESSAGE_LENGTH:,} characters.",
        )
    return text


def _last_user_message(run) -> str:
    """The most recent stored user turn, used when no new message is supplied."""
    for turn in reversed(list(run.messages or [])):
        if turn.get("role") == "user" and str(turn.get("content") or "").strip():
            return str(turn["content"]).strip()
    return ""


def _build_request(
    run,
    *,
    message: str,
    count: int | None = None,
    style_instruction: str | None = None,
    validity_check: bool | None = None,
) -> RunRequest:
    """Assemble a run request from a stored conversation plus the new turn.

    Settings fall back to what the conversation was started with, so a follow-up
    turn keeps the style instruction and validity setting the operator chose
    without the client having to resend them.
    """
    settings = run.settings or {}
    resolved_style = (
        style_instruction
        if style_instruction is not None
        else settings.get("style_instruction") or prompts.DEFAULT_STYLE_INSTRUCTION
    )
    resolved_validity = (
        validity_check
        if validity_check is not None
        else bool(settings.get("validity_check"))
    )
    resolved_count = _clamp_count(
        count if count is not None else settings.get("count", 1)
    )

    # History is what the model is shown; the new message is appended by the
    # agent itself, so the stored turn must not be duplicated here.
    history = [
        {"role": turn.get("role"), "content": turn.get("content")}
        for turn in (run.messages or [])
        if turn.get("role") in ("user", "assistant")
    ]

    return RunRequest(
        mode=run.mode,
        message=message,
        count=resolved_count,
        style_instruction=resolved_style,
        validity_check=resolved_validity,
        history=history,
        max_tool_calls=DEFAULT_MAX_TOOL_CALLS,
        # Resolved per request, so changing the window in Settings takes effect on
        # the next turn without a restart — the same contract the LLM client has.
        context_window=app_settings.resolve().context_window,
        # The operator pressing "Continue with these confidence rates" is what
        # releases a validity-gated run's prompt gate. Derived from the message
        # rather than a separate flag so the button and a typed equivalent behave
        # identically, and so an older client cannot release the gate by accident.
        released=prompts.is_release_message(message),
        # Read here rather than in the agent so a run is reproducible in a test and
        # a file replaced mid-turn cannot change a request already in flight.
        priority_sources=source_store.load(),
    )


def _persist_turn(
    db: Session,
    run,
    request: RunRequest,
    message: str,
    *,
    append_message: bool = True,
) -> None:
    """Store the new user turn and update the run's status before the agent runs.

    ``append_message=False`` is used for the opening turn, whose message the
    conversation already stored at creation time — appending it again would show
    the operator's question twice.
    """
    if append_message:
        runs.append_message(db, run, "user", message)
    run.status = ResearchRunStatus.RUNNING
    run.error = None
    # Keep the settings in step with the turn that is about to run.
    run.settings = {
        **(run.settings or {}),
        "style_instruction": request.style_instruction,
        "validity_check": request.validity_check,
        "count": request.count,
    }
    db.commit()


def _finish(db: Session, run, accumulated: dict, emitted: list[dict]) -> None:
    """Store a completed turn's transcript and derived result.

    The validity view is converted with ``to_dict`` rather than stored as the
    dataclass :func:`validity.describe` returns. ``result`` is a JSON column, so a
    dataclass raises ``TypeError: Object of type ValidityView is not JSON
    serializable`` — and because that happens *inside* the stream's ``finally``
    block, the turn is lost and the conversation stays RUNNING forever. It only
    bites the success path of the feature's flagship mode: a run without an
    assessment stores ``None``, which serialises fine.
    """
    runs.record_events(db, run, emitted)
    failed = bool(accumulated.get("error"))
    validity_view = validity.describe(accumulated.get("validity"))
    runs.finish_run(
        db,
        run,
        answer=accumulated.get("message", ""),
        result={
            "prompts": accumulated.get("prompts") or [],
            "sources": accumulated.get("sources") or [],
            "validity": validity_view.to_dict() if validity_view else None,
            "context": accumulated.get("context") or None,
            "notices": accumulated.get("notices") or [],
            "tool_calls": accumulated.get("tool_calls") or [],
            "thinking": accumulated.get("thinking") or "",
        },
        status=ResearchRunStatus.FAILED if failed else ResearchRunStatus.COMPLETED,
        error=accumulated.get("error", ""),
    )


def _record_persistence_failure(db: Session | None, run_id: str, exc: Exception) -> None:
    """Mark a run FAILED when its turn could not be stored.

    Best-effort, and deliberately separate from :func:`_finish`: the usual reason
    ``_finish`` raised is that something in the payload was not serialisable, and
    the same fault could hit this write too. Leaving the run at RUNNING is the one
    outcome that is definitely wrong — it reports an active turn that has ended.

    ``db`` may be ``None``, in which case the module's session factory is used;
    the streaming path has no request session of its own.
    """
    try:
        if db is not None:
            _mark_failed(db, run_id, exc)
            return
        with get_session_factory()() as session:
            _mark_failed(session, run_id, exc)
    except Exception:  # noqa: BLE001 - nothing further can be done here
        logger.exception("Could not mark research run %s as failed", run_id)


def _mark_failed(db: Session, run_id: str, exc: Exception) -> None:
    """Write the failure onto the run, if it still exists."""
    stored = runs.get_run(db, run_id)
    if stored is None:
        return
    stored.status = ResearchRunStatus.FAILED
    stored.error = (
        f"The turn finished but could not be saved: {type(exc).__name__}: {exc}"
    )
    db.commit()


def _summary(run) -> ResearchRunSummary:
    result = run.result or {}
    return ResearchRunSummary(
        id=run.id,
        title=run.title,
        seed_message=run.seed_message,
        mode=run.mode,
        status=run.status.value if hasattr(run.status, "value") else str(run.status),
        error=run.error,
        created_at=run.created_at,
        updated_at=run.updated_at,
        prompt_count=len(result.get("prompts") or []),
        has_validity=bool(result.get("validity")),
    )


# --------------------------------------------------------------------------- #
# Settings / vocabulary
# --------------------------------------------------------------------------- #

@router.get("/api/research/settings", response_model=ResearchSettingsResponse)
async def research_settings() -> ResearchSettingsResponse:
    """The research page's vocabulary and defaults.

    Served rather than duplicated in the frontend so the mode list, the default
    style instruction and the confidence disclaimer cannot drift between the two.
    """
    return ResearchSettingsResponse(
        modes=[dict(mode) for mode in MODES],
        default_style_instruction=prompts.DEFAULT_STYLE_INSTRUCTION,
        house_rules=prompts.HOUSE_RULES,
        max_prompts=MAX_PROMPTS,
        max_tool_calls=DEFAULT_MAX_TOOL_CALLS,
        disclaimer=validity.DISCLAIMER,
        # Served rather than hard-coded in the UI so the bar's thresholds and the
        # backend's folding decision cannot drift apart.
        context_window=app_settings.resolve().context_window,
        keep_recent_turns=context_module.KEEP_RECENT_TURNS,
        compact_at_share=context_module.COMPACT_AT_SHARE,
        warn_at_share=context_module.WARN_AT_SHARE,
        # The confidence target, served for the same reason: the card's verdict
        # and the agent's instruction must quote the same number.
        target_average=validity.TARGET_AVERAGE,
    )


# --------------------------------------------------------------------------- #
# Priority sources
# --------------------------------------------------------------------------- #

def _source_payload() -> dict:
    """The stored source list, in the shape the panel renders."""
    stored = source_store.load()
    if stored is None:
        return {
            "sources": [],
            "warnings": [],
            "filename": "",
            "template_version": sources.SCHEMA_VERSION,
        }
    return {
        **stored.to_dict(),
        "filename": source_store.stored_filename(),
        "template_version": sources.SCHEMA_VERSION,
    }


@router.get("/api/research/sources")
async def get_priority_sources() -> dict:
    """The operator's uploaded priority sources, if any.

    A plain dict rather than a response model: the payload is a pass-through of a
    file the operator wrote, and pinning it to a schema would make a new optional
    field in their file a 500 instead of something the agent can use.
    """
    return _source_payload()


@router.post("/api/research/sources")
async def upload_priority_sources(payload: dict) -> dict:
    """Validate and store an uploaded source file.

    Takes the raw text rather than a parsed structure: the file *is* the interface
    the operator works in, so the server must be the thing that reads it — a client
    that parsed it first would let a format error become a silent no-op.
    """
    text = str(payload.get("content") or "")
    filename = str(payload.get("filename") or "")
    try:
        parsed = source_store.save(text, filename=filename)
    except sources.SourceFileError as exc:
        # 400 with the reason: the operator is editing a file, so the message has
        # to say what is wrong with it rather than "invalid request".
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**parsed.to_dict(), "filename": source_store.stored_filename()}


@router.delete("/api/research/sources")
async def delete_priority_sources() -> dict:
    """Remove the stored source list, returning the run to its default behaviour."""
    source_store.clear()
    return _source_payload()


@router.get("/api/research/sources/template")
async def download_source_template() -> Response:
    """Download the exact JSON format the upload endpoint accepts.

    A downloadable file rather than documentation: the operator asked to be able to
    see the exact format, and a template that can be uploaded *unchanged* is a
    better specification than a description of one — it proves the format works.
    """
    return Response(
        content=sources.template_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="research-priority-sources.json"'
        },
    )


# --------------------------------------------------------------------------- #
# Conversations
# --------------------------------------------------------------------------- #

@router.get("/api/research/runs", response_model=ResearchRunListResponse)
async def list_research_runs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ResearchRunListResponse:
    """Every research conversation, newest first."""
    stored = runs.list_runs(db, limit=limit)
    return ResearchRunListResponse(
        items=[_summary(run) for run in stored], total=len(stored)
    )


@router.post("/api/research/runs", response_model=ResearchRunResponse, status_code=201)
async def create_research_run(
    request: ResearchRunRequest,
    db: Session = Depends(get_db),
) -> ResearchRunResponse:
    """Start a conversation and run the agent's first turn.

    The turn runs **synchronously** by default so the response carries the answer,
    which is what a script or a test wants. The research page instead passes
    ``stream_first: true`` and then streams the opening turn, because the live view
    — watching the agent think and open sites — is the feature, and a buffered
    first turn would show a blank screen for a minute before dumping the result.
    """
    mode = _validate_mode(request.mode)
    message = _clean_message(request.message)
    count = _clamp_count(request.count)

    mode_spec = next(spec for spec in MODES if spec["id"] == mode)
    # A mode that cannot produce prompts must not be told a prompt count, and the
    # validity tool is only offered where the mode supports it.
    effective_count = count if mode_spec["produces_prompts"] else 0
    validity_check = bool(request.validity_check) and mode_spec["supports_validity"]

    run = runs.create_run(
        db,
        mode=mode,
        message=message,
        settings={
            "style_instruction": request.style_instruction
            or prompts.DEFAULT_STYLE_INSTRUCTION,
            "validity_check": validity_check,
            "count": effective_count,
        },
    )

    if request.stream_first:
        # The caller will stream the turn. Leave the run RUNNING so the stream's
        # concurrency guard does not reject it as an already-running turn.
        return ResearchRunResponse(**runs.run_to_dict(run))

    agent_request = RunRequest(
        mode=mode,
        message=message,
        count=effective_count,
        style_instruction=run.settings["style_instruction"],
        validity_check=validity_check,
        history=[],
        max_tool_calls=DEFAULT_MAX_TOOL_CALLS,
        # Resolved here as well as in `_build_request`: this path builds its own
        # request, and a request with a zero window silently disables context
        # folding — so the opening turn of a long run would overflow where the
        # follow-up turns would not.
        context_window=app_settings.resolve().context_window,
        priority_sources=source_store.load(),
    )

    emitted, accumulated = _collect_with_session(agent_request)
    try:
        _finish(db, run, accumulated, emitted)
    except Exception as exc:  # noqa: BLE001 - reported, never a bare 500
        # The same serialisation fault the stream guards against can happen here,
        # and an unhandled 500 would lose the run entirely. The answer has already
        # been gathered, so the failure is recorded and the run still returned.
        logger.exception("Could not store research run %s", run.id)
        db.rollback()
        _record_persistence_failure(db, run.id, exc)
    return ResearchRunResponse(**runs.run_to_dict(run))


def _collect_with_session(request: RunRequest) -> tuple[list[dict], dict]:
    """Drain a run, returning the events and the derived result.

    Wrapped in its own session so a failure while draining cannot leave the
    request's session in a broken state, and so the streaming path can reuse it.
    """
    emitted: list[dict] = []
    accumulator = event_module.EventAccumulator()
    try:
        for payload in agent.run(request):
            emitted.append(payload)
            accumulator.add(payload)
    except Exception as exc:  # noqa: BLE001 - surface the failure as a run error
        logger.exception("Research run failed")
        failure = event_module.event(
            event_module.ERROR, text=f"{type(exc).__name__}: {exc}"
        )
        emitted.append(failure)
        accumulator.add(failure)
    return emitted, accumulator.to_dict()


@router.get("/api/research/runs/{run_id}", response_model=ResearchRunResponse)
async def get_research_run(
    run_id: str, db: Session = Depends(get_db)
) -> ResearchRunResponse:
    """One conversation, including its transcript so the UI can replay it."""
    run = _get_run_or_404(db, run_id)
    return ResearchRunResponse(**runs.run_to_dict(run))


@router.post("/api/research/runs/{run_id}/messages", response_model=ResearchRunResponse)
async def continue_research_run(
    run_id: str,
    request: ResearchFollowUpRequest,
    db: Session = Depends(get_db),
) -> ResearchRunResponse:
    """Continue a conversation and return the completed turn.

    The two confidence buttons post here with their canned message, which is why
    no separate "continue" endpoint exists: a button press and a typed sentence
    are the same operation, and giving them different endpoints is how the two
    paths drift apart.
    """
    run = _get_run_or_404(db, run_id)
    message = _clean_message(request.message)

    agent_request = _build_request(
        run,
        message=message,
        count=request.count,
        style_instruction=request.style_instruction,
        validity_check=request.validity_check,
    )
    _persist_turn(db, run, agent_request, message)

    emitted, accumulated = _collect_with_session(agent_request)
    try:
        _finish(db, run, accumulated, emitted)
    except Exception as exc:  # noqa: BLE001 - reported, never a bare 500
        logger.exception("Could not store research run %s", run.id)
        db.rollback()
        _record_persistence_failure(db, run.id, exc)
    return ResearchRunResponse(**runs.run_to_dict(run))


@router.get("/api/research/runs/{run_id}/stream")
async def stream_research_run(
    run_id: str,
    message: str | None = Query(default=None, max_length=MAX_MESSAGE_LENGTH),
    count: int | None = Query(default=None, ge=MIN_PROMPT_COUNT, le=MAX_PROMPTS),
    validity_check: bool | None = Query(default=None),
    session_factory=Depends(get_session_factory),
) -> StreamingResponse:
    """Continue a conversation, streaming each event as it happens.

    Server-Sent Events rather than WebSockets: the traffic is one-directional, it
    survives proxies that WebSockets do not, and a reconnect is a plain GET.

    The response is a **generator**, so the run only advances while the client is
    reading it. If the operator navigates away the iteration stops, which is the
    cheapest possible cancellation — the loop needs no flag to notice.

    A database session is opened inside the generator rather than injected,
    because FastAPI closes request-scoped dependencies before a streaming response
    body is consumed; using the injected session here would operate on a closed
    session. The same reason applies to persisting the finished turn.
    """
    # Read the run and validate up front, while the request session is open, so a
    # bad id or message is a normal 404/400 instead of an error mid-stream.
    with session_factory() as probe:
        run = runs.get_run(probe, run_id)
        if run is None:
            raise HTTPException(
                status_code=404, detail=f"Research run {run_id} does not exist."
            )
        if inflight.is_running(run_id):
            raise HTTPException(
                status_code=409,
                detail=(
                    "This conversation already has a turn running. Wait for it to "
                    "finish before sending another message."
                ),
            )
        cleaned_message = _clean_message(message) if message is not None else _last_user_message(run)
        if not cleaned_message:
            raise HTTPException(
                status_code=400,
                detail=(
                    "A message is required for the first turn of a conversation, or "
                    "the conversation must already contain one."
                ),
            )
        agent_request = _build_request(
            run, message=cleaned_message, count=count, validity_check=validity_check
        )
        # Persist the user turn and the settings before streaming, so a reload
        # during the run shows the message that is being answered. A first turn
        # already stored its message when the conversation was created, so it is
        # not appended twice.
        already_stored = bool(run.messages) and cleaned_message == _last_user_message(run)
        _persist_turn(
            probe, run, agent_request, cleaned_message, append_message=not already_stored
        )

    def generate() -> Iterator[str]:
        # Claim the conversation for this turn. Claiming *inside* the generator
        # (not before returning the response) means the claim is only taken once
        # the client actually starts reading, and it is released in `finally`
        # below — so a disconnect cannot leave the conversation claimed forever.
        if not inflight.begin(run_id):
            yield event_module.sse_frame(
                event_module.event(
                    event_module.ERROR,
                    text=(
                        "This conversation already has a turn running. Wait for it "
                        "to finish before sending another message."
                    ),
                )
            )
            yield event_module.SSE_DONE_FRAME
            return

        emitted: list[dict] = []
        accumulator = event_module.EventAccumulator()
        try:
            for payload in agent.run(agent_request):
                emitted.append(payload)
                accumulator.add(payload)
                yield event_module.sse_frame(payload)
        except Exception as exc:  # noqa: BLE001 - the stream must always end
            logger.exception("Streamed research run failed")
            failure = event_module.event(
                event_module.ERROR, text=f"{type(exc).__name__}: {exc}"
            )
            emitted.append(failure)
            accumulator.add(failure)
            yield event_module.sse_frame(failure)
        finally:
            inflight.end(run_id)
            # Persisting in `finally` means a client that disconnects mid-run
            # still leaves a usable thread with whatever was gathered, instead of
            # a conversation stuck at RUNNING forever.
            try:
                with session_factory() as session:
                    stored = runs.get_run(session, run_id)
                    if stored is not None:
                        _finish(session, stored, accumulator.to_dict(), emitted)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Could not persist research run %s", run_id)
                # A run left at RUNNING looks like it is still working, forever.
                # Recording the failure costs one more write and turns an
                # invisible loss into a thread the operator can see and retry.
                _record_persistence_failure(None, run_id, exc)
            yield event_module.SSE_DONE_FRAME

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


@router.post(
    "/api/research/runs/{run_id}/accept", response_model=ResearchAcceptResponse
)
async def accept_research_prompts(
    run_id: str,
    request: ResearchAcceptRequest,
    db: Session = Depends(get_db),
) -> ResearchAcceptResponse:
    """Push accepted prompts from a conversation into the Prompt Library.

    The library is where the pipeline starts, so an accepted prompt becomes a real
    prompt there — bindable to the images it produces, exactly like one written by
    hand.
    """
    run = _get_run_or_404(db, run_id)
    if not request.prompts:
        raise HTTPException(status_code=400, detail="No prompts were supplied.")
    if len(request.prompts) > MAX_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot accept more than {MAX_PROMPTS} prompts at once.",
        )

    outcome = runs.accept_prompts(
        db,
        run,
        request.prompts,
        tags=request.tags,
        negative_prompt=request.negative_prompt,
        details=request.details,
    )
    return ResearchAcceptResponse(**outcome)


@router.delete("/api/research/runs/{run_id}")
async def delete_research_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a conversation.

    Prompts already accepted into the library are kept — they are production
    work now, and deleting a research thread must not remove them.
    """
    run = _get_run_or_404(db, run_id)
    return runs.delete_run(db, run)


#: Re-exported so a test can assert the wire format without importing the module.
def encode_events(payloads: list[dict]) -> str:
    """Encode events as an SSE body. Used by tests."""
    return "".join(event_module.sse_frame(payload) for payload in payloads)


def events_as_jsonl(payloads: list[dict]) -> str:
    """Debug helper: one JSON object per line."""
    return "\n".join(json.dumps(payload, ensure_ascii=False) for payload in payloads)
