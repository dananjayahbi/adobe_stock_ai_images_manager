"""Per-mode system prompts for the Prompt Research agent.

The operator asked for one editable system prompt per mode — how prompts should
be structured, the template, the styles — as **one plain text** they can paste
and rewrite wholesale, with **no placeholders** and **no length limit**. This
module stores those texts in the ``app_settings`` document (flat keys, the same
convention ``source_store`` uses).

Contract
--------
* One text per canonical mode: ``research``, ``ideas``, ``generate``. Legacy
  ``static``/``batch`` runs (and their stored conversations) map to
  ``generate``, so an old thread still gets a sensible prompt.
* An empty or missing stored value means "use the shipped default" — the same
  reset-by-clearing contract the old house-style editor used.
* The text is **plain**: it is pasted verbatim into the system prompt with no
  substitution, no placeholders and no length limit. The operator wanted one
  box they can rewrite wholesale — structure, template, styles and rules all
  live here (the shipped default is the old style-note + style-instruction +
  house-rules block, so an untouched install behaves as before).

What stays outside this module
------------------------------
The tool-call protocol, the tool list, the answer format and the per-run
objective are *runtime* machinery assembled by ``compose_system_prompt``:
without them the agent cannot call tools or deliver a parseable answer, and the
objective is what encodes the validity gate. Everything else is operator
text.
"""

from __future__ import annotations

from services import app_settings

#: The canonical modes that have their own system prompt.
MODE_KEYS = ("research", "ideas", "generate")

#: Legacy stored runs map onto the canonical key that behaves like them.
_ALIASES = {"static": "generate", "batch": "generate"}

#: Storage keys in the ``app_settings`` document (flat, per house convention).
_KEY_PREFIX = "system_prompt_"


class SystemPromptError(ValueError):
    """Raised when a submitted system prompt cannot be stored.

    A :class:`ValueError` so the router can turn it into a 400 with the reason
    rather than a bare 500 — the operator is editing this text by hand.
    """


def key_for(mode: str) -> str:
    """The storage/effective key for any mode id, including legacy ones."""
    key = (mode or "").strip().lower()
    key = _ALIASES.get(key, key)
    return key if key in MODE_KEYS else "generate"


def default_template() -> str:
    """The shipped default: the old style-note + style-instruction + house-rules
    block, which used to be appended to every system prompt by the composer.

    Keeping it as the default means an untouched install sees no behaviour
    change, and the operator edits *one* text per mode instead of three fields.

    Imports :mod:`services.research.prompts` lazily: that module's
    ``compose_system_prompt`` imports *this* one, and a module-scope import the
    other way would be a cycle.
    """
    from services.research import prompts

    return (
        f"{prompts.STYLE_NOTE}\n\n"
        "STYLE INSTRUCTION (the operator's house standard):\n"
        f"{prompts.DEFAULT_STYLE_INSTRUCTION}\n\n"
        f"{prompts.HOUSE_RULES}"
    )


def effective(mode: str) -> str:
    """The template a run would use for ``mode`` (stored text or default).

    Never raises: a corrupt or hand-edited store must not stop a research run
    from starting, so a value of the wrong type is treated as unset.
    """
    raw = app_settings.load_raw()
    stored = raw.get(_KEY_PREFIX + key_for(mode))
    if isinstance(stored, str) and stored.strip():
        return stored
    return default_template()


def load_all() -> dict[str, tuple[str, bool]]:
    """``{mode: (effective_text, is_custom)}`` for the three canonical modes."""
    raw = app_settings.load_raw()
    default = default_template()
    out: dict[str, tuple[str, bool]] = {}
    for key in MODE_KEYS:
        stored = raw.get(_KEY_PREFIX + key)
        if isinstance(stored, str) and stored.strip():
            out[key] = (stored, True)
        else:
            out[key] = (default, False)
    return out


def save(mode: str, text: str) -> dict[str, tuple[str, bool]]:
    """Store the operator's system prompt for ``mode``.

    Empty text resets to the shipped default (the stored key is dropped rather
    than kept blank, so "is this modified" is one truthful check). No length
    limit is enforced — the operator asked for none, and the context window a
    run runs in is the natural bound.
    """
    key = (mode or "").strip().lower()
    if key not in MODE_KEYS:
        raise SystemPromptError(
            f"Unknown mode. Accepted values: {', '.join(MODE_KEYS)}."
        )
    value = "" if text is None else str(text)
    raw = app_settings.load_raw()
    if value.strip():
        raw[_KEY_PREFIX + key] = value.strip()
    else:
        raw.pop(_KEY_PREFIX + key, None)
    app_settings.save_raw(raw)
    return load_all()
