"""URLs the research agent already failed to read, refused before any network I/O.

Why this exists
---------------
``fetch_page`` fails in ways the agent cannot fix by retrying: an HTTP 403, a
25-second timeout, an anti-bot challenge, a page that loads but yields no text.
A model handed the same URL twice will do exactly that — burn two tool calls and
the wall-clock time of both to reach the identical failure. This module makes
the second attempt *impossible*: the first failure is recorded, and the guard in
``tools._tool_fetch_page`` refuses the call before a socket is ever opened.

Two behaviours fall out of one record:

* **Refusal** — ``is_blocked`` answers the pre-call guard in O(1).
* **Priority pruning** — a blocked URL that is also an operator priority source
  is removed from that list (see ``source_store.remove_url``), because a source
  that cannot be read can only drag the success rate down; the operator's list
  gets *more* reachable over time instead of less.

Why the ``app_settings`` document
---------------------------------
Same reasoning as ``source_store``: this is a single operator-facing record,
written atomically beside the rest of the settings, with no schema migration and
no table to manage. The document is only ever edited through this module.

Why an in-memory cache
----------------------
The guard runs before *every* fetch, and reading + parsing the settings document
each time would put disk I/O on the hot path of a call whose whole point is to
skip work. The cache is keyed by the **resolved settings path** because the test
suite (and only the test suite) redirects that path per test: keying on a
module-level constant would leak one test's blocked list into the next.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from services import app_settings
from services.research import sources

logger = logging.getLogger(__name__)

#: Key inside the settings document. Namespaced so it cannot collide with an LLM
#: field or with ``priority_sources``, and stable because an existing blocked
#: list must survive a version bump.
_STORE_KEY = "blocked_fetch_urls"

#: The document version this module writes.
_SCHEMA_VERSION = 1

#: Most blocked URLs kept. A cap because the list is rendered in the UI and
#: grows forever otherwise: a long-running deployment that brushes against
#: thousands of dead links should not accumulate a document no one can read, and
#: the oldest entries are the least likely to be retried anyway.
MAX_ENTRIES = 200

#: Resolved settings path -> canonical URL keys currently blocked. Guarded by
#: ``_cache_lock`` because ``fetch_page`` is called from worker threads while
#: the API writes from request handlers. Entries are popped (not updated in
#: place) on every write so the next read rebuilds from the document.
_cache_lock = threading.Lock()
_cache: dict[str, set[str]] = {}


def _path() -> Path:
    """Resolve the store path from settings on every call.

    Mirrors ``app_settings._path`` and reads the attribute each time rather
    than caching a module constant — that is what lets the per-test
    ``monkeypatch`` of ``APP_SETTINGS_PATH`` redirect this cache along with the
    store itself.
    """
    return Path(getattr(settings, "APP_SETTINGS_PATH", Path("app_settings.json")))


def _entries_from(raw: object) -> list[dict]:
    """The stored entries, tolerating anything malformed.

    Never raises: a corrupt record must not turn into a failed research run —
    the worst a bad entry can do here is look absent, and the next failure
    rewrites the document anyway.
    """
    if not isinstance(raw, dict):
        return []
    entries = raw.get("entries")
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def load() -> list[dict]:
    """The stored blocked entries, newest first. ``[]`` when none or unreadable."""
    return _entries_from(app_settings.load_raw().get(_STORE_KEY))


def _invalidate(path: Path) -> None:
    """Drop the cached keys for one settings path after a write to it."""
    with _cache_lock:
        _cache.pop(str(path), None)


def _cached_keys(path: Path) -> set[str]:
    """The blocked keys for ``path``, building them from disk on a miss.

    The common case — a URL that is *not* blocked — costs one dict lookup after
    the first call, with no file read. Only a known-blocked URL pays for a
    second read, and only to fetch the error message for the refusal text.
    """
    with _cache_lock:
        known = _cache.get(str(path))
    if known is None:
        keys: set[str] = set()
        for entry in load():
            key = sources.url_key(entry.get("url"))
            if key:
                keys.add(key)
        with _cache_lock:
            _cache[str(path)] = keys
        return keys
    return known


def is_blocked(url: str) -> tuple[bool, str]:
    """Whether ``url`` must be refused, and the error that blocked it.

    Returned as ``(blocked, last_error)`` so the guard message can say *why*
    the URL is on the list — "it previously failed (HTTP 403)" is what stops
    the model from reasoning that the block must be a transient glitch.
    """
    key = sources.url_key(url)
    if not key:
        # Nothing comparable (an empty argument): not blocked, and the caller's
        # own empty-URL check reports it properly.
        return False, ""
    path = _path()
    if key not in _cached_keys(path):
        return False, ""
    for entry in load():
        if sources.url_key(entry.get("url")) == key:
            return True, str(entry.get("error") or "")
    # The cache said blocked but the entry is gone: it was unblocked between
    # the cached read and now. Drop the stale entry rather than refusing a URL
    # the operator just released.
    _invalidate(path)
    return False, ""


def add_failure(url: str, error: str) -> dict:
    """Record one failed read and return the stored entry.

    A repeat failure of the same page bumps ``failures`` and refreshes the
    error and timestamp instead of appending a second entry: the blocked list
    answers "is this URL worth refusing", not "show me every attempt", and one
    row per page is what the UI renders.

    The entry keeps the URL *as the model asked for it* — the canonical key is
    only for comparison — so the operator recognises the link they saw in the
    transcript.
    """
    key = sources.url_key(url)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    document = app_settings.load_raw()
    entries = _entries_from(document.get(_STORE_KEY))

    for entry in entries:
        if sources.url_key(entry.get("url")) == key:
            entry["error"] = str(error or "")
            entry["blocked_at"] = now
            try:
                entry["failures"] = int(entry.get("failures") or 0) + 1
            except (TypeError, ValueError):
                entry["failures"] = 1
            break
    else:
        # New URL: prepend so the head of the list is always the most recent
        # failure, which is the one an operator scanning it cares about.
        entries.insert(
            0,
            {
                "url": str(url),
                "host": sources.PrioritySource(url=str(url)).host,
                "error": str(error or ""),
                "blocked_at": now,
                "failures": 1,
            },
        )

    # Cap by keeping the newest: entries are newest-first, so a plain slice
    # drops the oldest beyond the limit.
    entries = entries[:MAX_ENTRIES]

    document[_STORE_KEY] = {"version": _SCHEMA_VERSION, "entries": entries}
    app_settings.save_raw(document)
    _invalidate(_path())
    return next(
        (entry for entry in entries if sources.url_key(entry.get("url")) == key),
        entries[0] if entries else {},
    )


def remove(url: str) -> bool:
    """Release one blocked URL. ``True`` when it was actually on the list.

    A miss writes nothing: an unblock clicked twice should not rewrite the
    settings document, and the caller's response is the same either way.
    """
    key = sources.url_key(url)
    if not key:
        return False
    document = app_settings.load_raw()
    entries = _entries_from(document.get(_STORE_KEY))
    remaining = [
        entry for entry in entries if sources.url_key(entry.get("url")) != key
    ]
    if len(remaining) == len(entries):
        return False
    if remaining:
        document[_STORE_KEY] = {"version": _SCHEMA_VERSION, "entries": remaining}
    else:
        # Popping rather than storing an empty list, for the same reason
        # ``source_store.clear`` does: the document should read as "feature
        # never used", not "used, currently empty".
        document.pop(_STORE_KEY, None)
    app_settings.save_raw(document)
    _invalidate(_path())
    return True


def clear() -> None:
    """Release every blocked URL.

    Pops the key rather than writing ``{"entries": []}`` so the document is
    byte-identical to a fresh install's — the next read cannot tell "cleared"
    from "never blocked anything", which is exactly the state the feature
    should return to.
    """
    document = app_settings.load_raw()
    document.pop(_STORE_KEY, None)
    app_settings.save_raw(document)
    _invalidate(_path())
