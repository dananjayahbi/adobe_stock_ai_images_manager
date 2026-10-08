"""Where the operator's house style and house rules live between sessions.

Why this exists
---------------
The style instruction used to be **per-run React state**: the textarea was
seeded from ``services.research.prompts.DEFAULT_STYLE_INSTRUCTION`` on mount and
discarded on reload, so an operator who spent five minutes writing their house
standard lost it on every refresh. It was only ever persisted as a side effect
of *starting a run* (``run.settings["style_instruction"]``), which is why editing
it without running appeared not to save at all.

This module is the missing third state: the house standard itself, editable on
its own and applied to every run that does not override it.

Why a separate module from :mod:`services.research.source_store`
-------------------------------------------------------------
Both persist one operator preference into the same settings document, but they
have different contracts: a source file is parsed into a :class:`SourceSet` and
has a version, while these are two plain strings with a length bound and no
schema. Keeping them apart means neither module has to know about the other's
key names, and either can be removed without touching the other.

Storage
-------
Keys in the ``app_settings`` document (see :mod:`services.app_settings`), chosen
to match ``source_store``'s flat-key convention rather than nesting under a
sub-object, so a hand-edited file stays readable.

Empty means "use the built-in default"
--------------------------------------
A stored blank string is treated as *unset*, not as "run with no style". That is
the same contract :func:`source_store.load` uses, and it is deliberate: an empty
style instruction would produce a prompt with no standard at all, which is never
what an operator who cleared the box meant. The built-in default is always a
usable fallback, so clearing a field is a safe, reversible action and needs no
separate "reset" round trip.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from services import app_settings
from services.research import prompts

logger = logging.getLogger(__name__)

#: Namespaced so a future field cannot collide with an LLM or search setting.
_STYLE_KEY = "house_style_instruction"
_RULES_KEY = "house_rules"

#: Longest accepted value, in characters.
#:
#: These strings are pasted verbatim into every system prompt, so the bound is
#: about the context budget rather than about storage. A house standard that
#: exceeds it has stopped being a standard and started being a document, and the
#: cost is paid on *every* turn of *every* run. 8,000 characters is roughly two
#: thousand tokens — far longer than the built-in default, and comfortably inside
#: even the smallest supported model window once the tool list is added.
MAX_STYLE_CHARS = 8_000
MAX_RULES_CHARS = 8_000


class HouseStyleError(ValueError):
    """Raised when a submitted house-style value cannot be stored.

    A :class:`ValueError` so the router can turn it into a 400 with the reason,
    the same way a bad priority-source file is reported — the operator is editing
    this text by hand, so "invalid request" is not a useful answer.
    """


@dataclass(frozen=True)
class HouseStyle:
    """The operator's house standard, with the built-in defaults already applied.

    ``style_instruction`` and ``house_rules`` are the values a run would *use*,
    not the raw stored ones. Callers therefore never have to remember to fall
    back, and a cleared field reads as the default rather than as an empty
    system prompt.

    The ``*_is_custom`` flags distinguish "the operator wrote this" from "this is
    the shipped default", which is what the UI needs to decide whether to offer a
    Reset button. Derived here rather than in the client so the two cannot
    disagree about the same stored document.
    """

    style_instruction: str
    house_rules: str
    style_is_custom: bool
    rules_is_custom: bool


def _clean(value: object, *, field: str, limit: int) -> str:
    """Normalise a submitted value, rejecting what cannot be stored.

    Stripped rather than rejected on whitespace: trailing newlines are what a
    textarea produces, and storing them would make the "is this modified"
    comparison in the UI report a difference the operator never typed.
    """
    text = "" if value is None else str(value)
    if len(text) > limit:
        raise HouseStyleError(
            f"The {field} is longer than {limit:,} characters. It is pasted into "
            "every research prompt, so it needs to stay a short standard."
        )
    return text.strip()


def load() -> HouseStyle:
    """The effective house style, with the built-in defaults filled in.

    Never raises: a corrupt or hand-edited store must not stop a research run
    from starting, which is why a value of the wrong *type* is treated as unset
    rather than propagated into a system prompt.
    """
    raw = app_settings.load_raw()
    stored_style = raw.get(_STYLE_KEY)
    stored_rules = raw.get(_RULES_KEY)
    style = stored_style.strip() if isinstance(stored_style, str) else ""
    rules = stored_rules.strip() if isinstance(stored_rules, str) else ""
    return HouseStyle(
        style_instruction=style or prompts.DEFAULT_STYLE_INSTRUCTION,
        house_rules=rules or prompts.HOUSE_RULES,
        style_is_custom=bool(style),
        rules_is_custom=bool(rules),
    )


def effective_style() -> str:
    """Just the style instruction, for the call sites that need only that."""
    return load().style_instruction


def effective_rules() -> str:
    """Just the house rules, for the system prompt and the settings response."""
    return load().house_rules


def save(
    *,
    style_instruction: str | None = None,
    house_rules: str | None = None,
) -> HouseStyle:
    """Validate and persist a partial update, returning the new effective style.

    Both fields are validated **before** anything is written, so a rejected
    update leaves the previously working text in place rather than half-applying
    it. ``None`` means "leave this field alone"; an empty string means "use the
    built-in default again", which is stored by removing the key so the document
    returns to its pre-edit state rather than carrying a meaningless blank.
    """
    if style_instruction is not None:
        _clean(style_instruction, field="style instruction", limit=MAX_STYLE_CHARS)
    if house_rules is not None:
        _clean(house_rules, field="house rules", limit=MAX_RULES_CHARS)

    document = app_settings.load_raw()
    for key, value in (
        (_STYLE_KEY, style_instruction),
        (_RULES_KEY, house_rules),
    ):
        if value is None:
            continue
        if value.strip():
            document[key] = value.strip()
        else:
            document.pop(key, None)
    app_settings.save_raw(document)
    return load()


def reset(*, style_instruction: bool = False, house_rules: bool = False) -> HouseStyle:
    """Restore one or both fields to the built-in default.

    Equivalent to :func:`save` with an empty value, kept as a named function
    because "put the shipped default back" is a different intent from "I typed an
    empty box", and a caller that wants one should not have to construct it.
    """
    return save(
        style_instruction="" if style_instruction else None,
        house_rules="" if house_rules else None,
    )