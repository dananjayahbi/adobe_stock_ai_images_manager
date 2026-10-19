"""The image-generation brief behind a record, as metadata context.

A separate module from ``gemini_metadata`` for the usual reason: that module
builds prompts and must stay free of database access (its tests fake the LLM
call and nothing else), while this is the one place that reads the ``prompts``
table to answer "what was this image asked to be". Both orchestrators call it
so the binding rules - what counts as a brief, what gets excluded, how much
survives truncation - are written once.

``negative_prompt`` is deliberately NOT part of the brief: it lists what must
*not* appear, and handing exclusions to a model that writes descriptions
invites them straight into the output.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models import Prompt

logger = logging.getLogger(__name__)

#: Longest brief handed to the model. A brief is context beside the pixels,
#: not a second document to describe - 1500 characters covers a thorough
#: generation prompt while leaving the majority of the prompt budget to the
#: task itself.
MAX_BRIEF_CHARS = 1_500


def brief_for(session: Session, prompt_id: str | None) -> str:
    """The generation brief bound to ``prompt_id``, or ``""`` when there is none.

    Empty for every "nothing to add" case - no binding, a deleted prompt row,
    a title and body that are both blank - so a record without a brief produces
    byte-identical prompts to one from before this context existed.

    Never raises: a context read must not be able to fail the metadata
    generation it feeds, so any database error logs and returns ``""``.
    """
    if not prompt_id:
        return ""
    try:
        row = session.get(Prompt, prompt_id)
    except Exception:  # noqa: BLE001 - context must not fail the call it feeds
        logger.warning("Could not read prompt %s for metadata context", prompt_id)
        return ""
    if row is None:
        return ""

    title = (row.title or "").strip()
    body = (row.body or "").strip()
    if not title and not body:
        return ""

    parts: list[str] = []
    if title:
        # Labelled so the model reads the two differently-shaped texts for
        # what they are: a short folder-style name, then the raw brief.
        parts.append(f"Title: {title}")
    if body:
        parts.append(body)
    brief = "\n".join(parts)
    if len(brief) > MAX_BRIEF_CHARS:
        brief = brief[:MAX_BRIEF_CHARS].rstrip() + "…"
    return brief
