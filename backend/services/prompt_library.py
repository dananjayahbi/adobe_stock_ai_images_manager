"""Prompt Library domain helpers.

The Prompt Library is the *source* side of Stage 1: the operator writes the
generation prompts first, then collects the images they produced and binds them
back to the prompt.

Keeping the derivation rules here (rather than in the router) means the rules
are testable without HTTP and are shared by every entry point:

- how a display title is derived from a prompt body,
- how binding counts are computed,
- when a prompt flips between DRAFT and USED.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import ImageRecord, Prompt, PromptStatus

#: Longest derived title, matching the ``title`` column width.
MAX_TITLE_LENGTH = 200

#: Collapse any run of whitespace so a multi-line prompt yields one clean title.
_WHITESPACE = re.compile(r"\s+")


def derive_title(body: str, fallback: str = "Untitled prompt") -> str:
    """Build a readable title from a prompt body's first line.

    Prompts are usually written as free text, so a separate title field would
    often be left empty. Deriving one from the first sentence keeps prompt
    blocks scannable in the sidebar without forcing extra typing.
    """
    text = (body or "").strip()
    if not text:
        return fallback

    # First non-empty line, then its first sentence, so a long paragraph does
    # not become a 200-character title.
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    first_line = _WHITESPACE.sub(" ", first_line).strip()
    sentence = first_line.split(". ")[0].strip()

    if not sentence:
        return fallback
    if len(sentence) <= MAX_TITLE_LENGTH:
        return sentence
    return sentence[: MAX_TITLE_LENGTH - 1].rstrip() + "…"


def normalise_tags(tags: list[str] | None) -> list[str] | None:
    """Trim, de-duplicate (case-insensitively), and drop empty tags."""
    if not tags:
        return None
    seen: set[str] = set()
    cleaned: list[str] = []
    for tag in tags:
        value = (tag or "").strip()
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        cleaned.append(value)
    return cleaned or None


def binding_counts(db: Session) -> Counter[str]:
    """How many records are bound to each prompt.

    Computed with one grouped query instead of a per-prompt count so the list
    endpoint stays O(1) in queries regardless of library size.
    """
    rows = db.execute(
        select(ImageRecord.prompt_id, func.count(ImageRecord.id))
        .where(ImageRecord.prompt_id.isnot(None))
        .group_by(ImageRecord.prompt_id)
    ).all()
    return Counter({prompt_id: count for prompt_id, count in rows})


def apply_binding_status(prompt: Prompt, bound_count: int) -> None:
    """Reflect the binding count on the prompt's status.

    Binding an image *automatically* marks the prompt used — that is the whole
    point of tracking the link. The reverse is deliberately NOT automatic:
    unbinding the last image leaves the prompt USED, because the operator may
    have consumed it elsewhere, and silently reverting an explicit manual
    "mark as used" would be worse than leaving it. Only DRAFT is auto-promoted.
    """
    if bound_count > 0 and prompt.status == PromptStatus.DRAFT:
        prompt.status = PromptStatus.USED
        prompt.used_at = prompt.used_at or datetime.now(timezone.utc)


def sync_used_status(db: Session, prompt: Prompt, bound_count: int | None = None) -> None:
    """Apply the derived status for one prompt, optionally counting first."""
    if bound_count is None:
        bound_count = (
            db.execute(
                select(func.count(ImageRecord.id)).where(
                    ImageRecord.prompt_id == prompt.id
                )
            ).scalar_one()
        )
    apply_binding_status(prompt, bound_count)


def prompt_to_dict(prompt: Prompt, bound_count: int = 0) -> dict:
    """Serialise a prompt into the shape ``PromptResponse`` expects.

    ``tags`` is normalised here because a legacy row may hold a non-list value
    in the JSON column, and ``bound_count`` is always supplied by the caller so
    the response never claims zero bindings by accident.
    """
    tags = prompt.tags if isinstance(prompt.tags, list) else None
    params = prompt.params if isinstance(prompt.params, dict) else None
    return {
        "id": prompt.id,
        "title": prompt.title,
        "body": prompt.body,
        "negative_prompt": prompt.negative_prompt,
        "params": params,
        "tags": tags,
        "status": prompt.status,
        "used_at": prompt.used_at,
        "created_at": prompt.created_at,
        "updated_at": prompt.updated_at,
        "bound_count": bound_count,
    }
