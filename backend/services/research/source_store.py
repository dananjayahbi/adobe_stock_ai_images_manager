"""Where the operator's uploaded priority-source file lives.

Kept in the ``app_settings`` document rather than a table of its own, for the same
reason the LLM settings are: it is a single operator preference, not relational
data, and storing it beside the settings means one atomic write and no migration.

Why a *separate* module from :mod:`services.research.sources`
------------------------------------------------------------
``sources`` is pure: it parses text into a :class:`~services.research.sources.SourceSet`
and knows nothing about storage. This module is the only place that touches the
filesystem, so the parser can be tested without one and a change to where the file
lives cannot change how it is read.
"""

from __future__ import annotations

import logging

from services import app_settings
from services.research import sources

logger = logging.getLogger(__name__)

#: Key inside the settings document. Namespaced so it cannot collide with an LLM
#: field, and stable because an existing upload must survive a version bump.
_STORE_KEY = "priority_sources"

#: The uploaded file's original name, kept only so the UI can say which file is
#: loaded. Purely informational — the sources themselves are stored parsed.
_NAME_KEY = "priority_sources_filename"

#: Longest accepted upload, in characters. A source list is a few hundred bytes; a
#: multi-megabyte file is a mistake (or an attempt to crowd out the prompt), and
#: parsing it would be wasted work either way.
MAX_UPLOAD_CHARS = 200_000


def load() -> sources.SourceSet | None:
    """The stored source set, or ``None`` when nothing is uploaded.

    ``None`` rather than an empty set, because the two mean different things: no
    file means the feature is off and the prompt must be unchanged, while a file
    that parsed to nothing is a fault the operator needs to see.
    """
    raw = app_settings.load_raw().get(_STORE_KEY)
    if not isinstance(raw, dict):
        return None
    stored = raw.get("sources")
    if not isinstance(stored, list) or not stored:
        return None
    try:
        parsed = sources.parse({"version": raw.get("version"), "sources": stored})
    except sources.SourceFileError:
        # A stored file that no longer parses is logged, not raised: it must not
        # stop a research run from starting. The upload path validates first, so
        # reaching here means the format changed under a saved file.
        logger.exception("The stored priority-source file could not be read")
        return None
    return parsed


def stored_filename() -> str:
    """The name of the uploaded file, for display. Empty when none is stored."""
    name = app_settings.load_raw().get(_NAME_KEY)
    return str(name) if isinstance(name, str) else ""


def save(text: str, *, filename: str = "") -> sources.SourceSet:
    """Validate and store an uploaded file.

    Validated *before* anything is written, so a bad upload leaves the previously
    working list in place rather than replacing it with nothing. Raises
    :class:`services.research.sources.SourceFileError` with the reason.
    """
    if len(text or "") > MAX_UPLOAD_CHARS:
        raise sources.SourceFileError(
            f"The file is larger than {MAX_UPLOAD_CHARS:,} characters. A source "
            "list is normally a few hundred bytes."
        )
    parsed = sources.parse_text(text)

    document = app_settings.load_raw()
    document[_STORE_KEY] = {
        "version": sources.SCHEMA_VERSION,
        "sources": [source.to_dict() for source in parsed.sorted()],
    }
    if filename:
        document[_NAME_KEY] = " ".join(filename.split())[:120]
    app_settings.save_raw(document)
    return parsed


def clear() -> None:
    """Remove the stored source list.

    Pops the keys rather than writing empty lists, so ``load`` sees the same state
    it would after a fresh install — the feature is off and the prompt is
    unchanged.
    """
    document = app_settings.load_raw()
    document.pop(_STORE_KEY, None)
    document.pop(_NAME_KEY, None)
    app_settings.save_raw(document)
