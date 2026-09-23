"""Persistence for Prompt Research conversations.

The database work for the feature, kept out of the router so it is testable
without HTTP and so the *rules* about what a conversation contains live in one
place:

* a conversation is append-only in practice — a follow-up turn adds messages and
  replaces the derived result, it never rewrites history;
* the event transcript is capped, because a long research thread would otherwise
  grow without bound in a JSON column;
* a prompt accepted into the Prompt Library is recorded on the run, so the
  operator can see which of the run's prompts were kept.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Prompt, PromptStatus, ResearchRun, ResearchRunStatus
from services import prompt_library
from services.research import events as event_module

logger = logging.getLogger(__name__)

#: Longest stored transcript, in events. A research run emits one event per
#: streamed token fragment, so an uncapped list would be enormous; the tail is
#: what a reload needs to show.
MAX_STORED_EVENTS = 600

#: Longest conversation kept on the run, in turns. Matches the agent's own
#: history window so what is stored is what the model is shown.
MAX_STORED_MESSAGES = 40

#: Longest title derived from the opening message.
MAX_TITLE_LENGTH = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def derive_title(message: str, mode: str) -> str:
    """A readable thread title from the opening message.

    Derived rather than asked for: the operator is mid-thought when they start a
    thread, and a required title field would be a worse experience than a title
    they can see and ignore.
    """
    text = " ".join((message or "").split())
    if not text:
        return f"New {mode} research"
    if len(text) <= MAX_TITLE_LENGTH:
        return text
    return text[: MAX_TITLE_LENGTH - 1].rstrip() + "…"


def create_run(
    db: Session,
    *,
    mode: str,
    message: str,
    settings: dict | None = None,
) -> ResearchRun:
    """Create a conversation and store the opening user turn."""
    run = ResearchRun(
        title=derive_title(message, mode),
        seed_message=message,
        mode=mode,
        status=ResearchRunStatus.RUNNING,
        messages=[{"role": "user", "content": message, "created_at": _now().isoformat()}],
        events=[],
        settings=settings or {},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> ResearchRun | None:
    return db.execute(
        select(ResearchRun).where(ResearchRun.id == run_id)
    ).scalar_one_or_none()


def list_runs(db: Session, *, limit: int = 50) -> list[ResearchRun]:
    """Conversations, newest first."""
    return list(
        db.execute(
            select(ResearchRun).order_by(ResearchRun.created_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )


def append_message(db: Session, run: ResearchRun, role: str, content: str) -> None:
    """Add one conversation turn, trimming the oldest beyond the cap."""
    messages = list(run.messages or [])
    messages.append({"role": role, "content": content, "created_at": _now().isoformat()})
    if len(messages) > MAX_STORED_MESSAGES:
        messages = messages[-MAX_STORED_MESSAGES:]
    run.messages = messages


def coalesce_events(events: list[dict]) -> list[dict]:
    """Merge consecutive streamed text fragments into one event each.

    A streaming run emits one ``thinking`` and one ``message`` event **per token
    fragment**, so a single 48-second turn produced 600 events — exactly the
    storage cap, which meant the transcript was trimmed from the front and a
    reloaded page started mid-run.

    Coalescing preserves the text and the ordering while cutting the count by
    roughly two orders of magnitude, so the cap is never reached in normal use.
    Only the two append-only text types are merged; every other event is a
    discrete fact (a tool call, a source, a score) whose position matters.
    """
    merged: list[dict] = []
    for payload in events:
        event_type = payload.get("type")
        if (
            event_type in (event_module.THINKING, event_module.MESSAGE)
            and merged
            and merged[-1].get("type") == event_type
        ):
            previous = merged[-1]
            merged[-1] = {**previous, "text": previous.get("text", "") + payload.get("text", "")}
            continue
        merged.append(dict(payload))
    return merged


def record_events(db: Session, run: ResearchRun, events: list[dict]) -> None:
    """Store a run's transcript, keeping the most recent events.

    Events are coalesced first (see :func:`coalesce_events`) so the cap is a
    safety net rather than something a normal run reaches. Trimming from the
    *front* loses the earliest steps of an unusually long run, which is the right
    trade: the result, the sources and the prompts are kept separately in
    ``result``, so only the play-by-play of the opening turns is dropped.
    """
    stored = list(run.events or [])
    stored.extend(coalesce_events(events))
    if len(stored) > MAX_STORED_EVENTS:
        stored = stored[-MAX_STORED_EVENTS:]
    run.events = stored


def finish_run(
    db: Session,
    run: ResearchRun,
    *,
    answer: str,
    result: dict,
    status: ResearchRunStatus = ResearchRunStatus.COMPLETED,
    error: str = "",
) -> ResearchRun:
    """Close a run: store the answer, the derived result and the final status."""
    if answer:
        append_message(db, run, "assistant", answer)
    run.result = result
    run.status = status
    run.error = error or None
    db.commit()
    db.refresh(run)
    return run


def run_to_dict(run: ResearchRun, *, include_events: bool = True) -> dict:
    """Serialise a conversation for the API."""
    payload = {
        "id": run.id,
        "title": run.title,
        "seed_message": run.seed_message,
        "mode": run.mode,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "messages": list(run.messages or []),
        "result": run.result or {},
        "settings": run.settings or {},
        "error": run.error,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }
    if include_events:
        payload["events"] = list(run.events or [])
    return payload


def accept_prompts(
    db: Session,
    run: ResearchRun,
    bodies: list[str],
    *,
    tags: list[str] | None = None,
    negative_prompt: str | None = None,
    details: list[dict] | None = None,
) -> dict:
    """Push accepted prompts from a run into the Prompt Library.

    The bridge between research and production: a prompt the operator accepted
    becomes a real library prompt, so it can be bound to the images it produces
    exactly like a hand-written one.

    ``details`` optionally carries the metadata the JSON contract supplied —
    title, tags, category — positionally matching ``bodies``. Without it the
    title is derived from the body, which is what an operator who typed the body
    by hand would get anyway.

    Prompts arrive as **DRAFT** and are not marked used, because a newly written
    prompt has not produced anything yet — the library's own rules promote it when
    an image is bound.

    Duplicates are skipped rather than refused: asking twice (a double click, a
    re-run) should not create two identical library entries, but it should also
    not fail the second request.
    """
    existing = {
        (body or "").strip()
        for body in db.execute(select(Prompt.body)).scalars().all()
    }

    supplied = list(details or [])
    created: list[dict] = []
    skipped: list[str] = []

    for position, body in enumerate(bodies):
        cleaned = (body or "").strip()
        if not cleaned:
            continue
        if cleaned in existing:
            skipped.append(cleaned)
            continue

        meta = supplied[position] if position < len(supplied) else {}
        if not isinstance(meta, dict):
            meta = {}

        # The model's own title wins when it supplied one; otherwise the body is
        # summarised, which is what a hand-written prompt gets.
        title = str(meta.get("title") or "").strip()
        title = (title or prompt_library.derive_title(cleaned))[:200]

        # Per-prompt tags are merged with the run-level tags rather than
        # replacing them: the run-level ones are the operator's own grouping.
        merged_tags = prompt_library.normalise_tags(
            list(tags or []) + list(meta.get("tags") or [])
        )

        params: dict = {"source": "prompt_research", "research_run_id": run.id}
        category = meta.get("category")
        if isinstance(category, int) and not isinstance(category, bool):
            params["category"] = category

        prompt = Prompt(
            title=title,
            body=cleaned,
            negative_prompt=(negative_prompt or "").strip() or None,
            params=params,
            tags=merged_tags,
            status=PromptStatus.DRAFT,
        )
        db.add(prompt)
        existing.add(cleaned)
        created.append({"id": prompt.id, "title": title, "body": cleaned})

    if created:
        db.commit()
        # Refresh to read the generated ids and timestamps back.
        for entry in created:
            stored = db.get(Prompt, entry["id"])
            if stored is not None:
                entry["id"] = stored.id

    # Record which prompts of this run were kept, so the thread can show it.
    result = dict(run.result or {})
    accepted = list(result.get("accepted_prompt_ids") or [])
    accepted.extend(entry["id"] for entry in created)
    result["accepted_prompt_ids"] = accepted
    run.result = result
    db.commit()

    return {"created": created, "skipped": skipped, "count": len(created)}


def delete_run(db: Session, run: ResearchRun) -> dict:
    """Delete a conversation.

    Only the thread is removed. Any prompt already accepted into the library
    stays there, because it is now a real prompt that may already have images
    bound to it — deleting a research thread must not delete production work.
    """
    db.delete(run)
    db.commit()
    return {"deleted": 1}
