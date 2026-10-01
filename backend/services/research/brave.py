"""Brave Search — the authenticated primary provider, when the operator enables it.

Why this module exists
----------------------
The unauthenticated DuckDuckGo front-end is a *scrape*, and it behaves like one:
it rate-limits aggressively (measured on this machine: eight queries in three
seconds got the anti-bot challenge on all eight) and a markup change silently
yields zero results. Brave Search is a documented JSON API behind a key, so it is
both more reliable and honest to parse.

Provider order
--------------
The chain is decided by settings, not hard-coded — see
:func:`services.research.search.provider_chain`:

1. **Brave**, whenever the operator has enabled it and stored a key. It becomes
   the *default* search the moment it is configured.
2. **DuckDuckGo** — the **same tier** as Brave (a general web index), so falling
   back to it is **silent**. The results are the same kind of evidence.
3. **Google News RSS** — a **different tier**. Editorial coverage is not
   catalogue data, so a result from here is marked as a *degraded source* and the
   tool text says so.

That tier distinction is the load-bearing part. Falling back from Brave to
DuckDuckGo must not tell the operator their results are "news and editorial
coverage" — which is exactly what a single ``used_fallback`` flag would have done.

API contract (verified against the vendor documentation)
--------------------------------------------------------
* ``GET https://api.search.brave.com/res/v1/web/search?q=…&count=N``
* ``X-Subscription-Token: <key>`` is the only auth mechanism.
* ``count`` is capped at **20** by the API.
* The payload is ``{"web": {"results": [{"title", "url", "description",
  "extra_snippets", "profile": {"long_name"}}]}}``.
* Failures: ``401``/``403`` an unusable key, ``422`` a rejected query, ``429``
  rate limit exceeded — each with a body of
  ``{"error": {"code", "status", "detail"}}``.

Every failure returns ``ok=False`` with a message naming the condition, so the
orchestrator can fall through to the next provider *and* the operator can still
be told which provider refused and why.
"""

from __future__ import annotations

import gzip
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from services.research.search import (
    MAX_BODY_BYTES,
    MAX_QUERY_LENGTH,
    USER_AGENT,
    SearchResponse,
    SearchResult,
    clean_fragment,
)

logger = logging.getLogger(__name__)

#: The web-search endpoint. ``/res/v1`` is the versioned REST root.
ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

#: Provider identity, recorded on every response so the UI can name the source.
PROVIDER_NAME = "brave"
PROVIDER_LABEL = "Brave Search"

#: The header Brave authenticates with. Not ``Authorization``: a bearer token is
#: silently ignored and the request comes back 401, which reads like a bad key.
API_KEY_HEADER = "X-Subscription-Token"

#: Brave rejects ``count`` above 20 with a 422.
MAX_COUNT = 20

#: How many ``extra_snippets`` to fold into the snippet. The agent reads snippets
#: rather than whole pages, and Brave returns up to five; two more than the
#: description is useful without making one result dominate the tool output.
MAX_EXTRA_SNIPPETS = 2

#: HTTP statuses that mean "this provider cannot answer right now" and should
#: send the orchestrator to the next one. Named rather than inlined so the
#: operator-facing message and the fallback decision cannot disagree.
_STATUS_RATE_LIMITED = 429
_STATUS_UNAUTHORISED = (401, 403)
_STATUS_BAD_QUERY = 422


def parse_payload(payload: dict, limit: int) -> list[SearchResult]:
    """Extract organic results from a Brave JSON payload.

    Kept pure and separate from the request so the shape handling is testable
    against a captured payload with no network call.

    The publisher name lives in ``profile.long_name`` (e.g. "Adobe Stock") and is
    the useful part for judging a source, so it becomes the display URL when it is
    present — the same convention the news provider uses.
    """
    web = payload.get("web") if isinstance(payload, dict) else None
    raw_results = (web or {}).get("results") or []

    results: list[SearchResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        if not url or not title:
            continue

        description = str(item.get("description") or "").strip()
        extras = item.get("extra_snippets") or []
        extra_text = " ".join(
            str(entry).strip()
            for entry in list(extras)[:MAX_EXTRA_SNIPPETS]
            if str(entry).strip()
        )
        snippet = " ".join(part for part in (description, extra_text) if part)

        profile = item.get("profile") or {}
        display = str(
            profile.get("long_name") or profile.get("name") or ""
        ).strip()

        results.append(
            SearchResult(
                title=clean_fragment(title),
                url=url,
                snippet=clean_fragment(snippet),
                display_url=display or url,
            )
        )
        if len(results) >= limit:
            break
    return results


def _read_body(response) -> str:  # noqa: ANN001 - the http response object
    """Decode a response body, transparently un-gzipping it.

    Brave's documentation asks clients to send ``Accept-Encoding: gzip``.
    ``urllib`` does **not** decompress for us, so without this a successful
    response decodes to binary noise and the provider looks like it returned no
    results — a silent, misleading failure.
    """
    raw = response.read(MAX_BODY_BYTES)
    encoding = str(response.headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        try:
            raw = gzip.decompress(raw)
        except OSError:  # noqa: PERF203 - a truncated stream must not be fatal
            logger.warning("Brave response claimed gzip but could not be decompressed")
    return raw.decode("utf-8", "replace")


def _describe_http_error(code: int, body: str) -> str:
    """A message naming the condition, using Brave's own detail when it sent one."""
    detail = ""
    try:
        payload = json.loads(body or "{}")
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            detail = str(error.get("detail") or error.get("code") or "").strip()
    except (ValueError, AttributeError):
        detail = ""

    if code == _STATUS_RATE_LIMITED:
        reason = (
            "the plan's request rate limit was exceeded"
            if not detail
            else f"the plan's request rate limit was exceeded ({detail})"
        )
    elif code in _STATUS_UNAUTHORISED:
        reason = (
            "the API key was rejected — check it was copied in full and is "
            "still active"
            if not detail
            else f"the API key was rejected ({detail})"
        )
    elif code == _STATUS_BAD_QUERY:
        reason = "the query was rejected as invalid" if not detail else detail
    else:
        reason = detail or "the request failed"

    return f"{PROVIDER_LABEL} returned HTTP {code}: {reason}"


def brave_search(
    query: str, *, api_key: str, limit: int, timeout: int
) -> SearchResponse:
    """Run one query against the Brave Web Search API.

    Returns ``ok=False`` for every failure rather than raising, so the
    orchestrator can fall through to the next provider. The error string always
    names the condition, because "rate-limited" and "bad key" need different
    operator reactions.
    """
    cleaned = urllib.parse.quote_plus(
        (query or "").strip()[:MAX_QUERY_LENGTH]
    )
    if not cleaned:
        return SearchResponse(query="", ok=False, error="Empty query.")

    if not (api_key or "").strip():
        # Reached only if the chain was built without a key, which the settings
        # validation is supposed to prevent. Reported rather than skipped so a
        # configuration fault is visible instead of looking like a dead provider.
        return SearchResponse(
            query=query,
            ok=False,
            error=f"{PROVIDER_LABEL} is enabled but no API key is configured",
        )

    url = f"{ENDPOINT}?q={cleaned}&count={max(1, min(limit, MAX_COUNT))}"
    request = urllib.request.Request(
        url,
        headers={
            API_KEY_HEADER: api_key.strip(),
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = _read_body(response)
    except urllib.error.HTTPError as exc:
        try:
            error_body = _read_body(exc)
        except Exception:  # noqa: BLE001 - the status is the useful part
            error_body = ""
        message = _describe_http_error(exc.code, error_body)
        logger.warning("Brave search failed for %r: %s", query, message)
        return SearchResponse(query=query, ok=False, error=message)
    except Exception as exc:  # noqa: BLE001 - every failure becomes a reported step
        logger.warning("Brave search failed for %r: %s", query, exc)
        return SearchResponse(
            query=query, ok=False, error=f"{type(exc).__name__}: {exc}"
        )

    try:
        payload = json.loads(body or "{}")
    except ValueError:
        return SearchResponse(
            query=query,
            ok=False,
            error=f"{PROVIDER_LABEL} returned a response that was not JSON",
        )

    results = parse_payload(payload, limit=limit)
    if not results:
        # A 200 with no results is reported as degraded, not empty: Brave omits
        # `web.results` entirely for some query shapes, and "the provider
        # answered but produced nothing readable" is a different fact from "the
        # web has nothing to say about this".
        return SearchResponse(
            query=query,
            ok=False,
            error=(
                f"{PROVIDER_LABEL} answered but returned no readable web results "
                "for this query"
            ),
        )

    response = SearchResponse(query=query, results=results)
    response.provider = PROVIDER_NAME
    response.provider_label = PROVIDER_LABEL
    return response
