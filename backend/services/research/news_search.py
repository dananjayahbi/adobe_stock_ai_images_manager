"""A second web-search provider: Google News RSS.

Why a fallback provider exists at all
-------------------------------------
The primary provider (DuckDuckGo's lite front-end) works well, but it is an
unauthenticated HTML endpoint and it **rate-limits aggressively**. Measured on
this machine: a burst of eight queries in three seconds got the anti-bot
challenge on all eight, and the block then persisted for a while. A research run
issues several queries, so a single-provider design fails exactly when it is
being used hardest.

A failure is not silently tolerated: the orchestrator in
:mod:`services.research.search` tries each provider in turn and, if all fail,
reports the failure so the agent cannot read it as "no competition". What this
module adds is a *second chance* from a different host with different limits.

Why this provider
-----------------
It is a public RSS feed: no key, no HTML scraping, a stable documented shape, and
it answers reliably. It also returns something the HTML providers do not —
**dated, attributed articles**, which is exactly the evidence a validity
assessment needs ("what is being written about this niche, and by whom").

The limitation is stated rather than hidden: news coverage is editorial, not
marketplace catalogue data, so it cannot show how many competing *stock images*
exist. The tool text says so, so the agent does not over-read it.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from services.research.search import (
    MAX_BODY_BYTES,
    MAX_QUERY_LENGTH,
    USER_AGENT,
    SearchResponse,
    SearchResult,
    looks_blocked,
)

logger = logging.getLogger(__name__)

#: The feed endpoint. ``hl``/``gl``/``ceid`` pin the edition to US English, so a
#: query is not answered with a differently-localised result set.
ENDPOINT = "https://news.google.com/rss/search"

#: Provider id, recorded on the response so the UI can say where results came from.
PROVIDER_NAME = "google_news"
PROVIDER_LABEL = "Google News"

_ITEM = re.compile(r"<item>(?P<body>.*?)</item>", re.S)
_TITLE = re.compile(r"<title>(?P<text>.*?)</title>", re.S)
_LINK = re.compile(r"<link>(?P<text>.*?)</link>", re.S)
_PUB_DATE = re.compile(r"<pubDate>(?P<text>.*?)</pubDate>", re.S)
_SOURCE = re.compile(
    r'<source\s+url="(?P<url>[^"]*)"[^>]*>(?P<name>.*?)</source>', re.S
)
_TAG = re.compile(r"<[^>]+>")


def _clean(raw: str) -> str:
    """Strip markup and entities from a feed fragment."""
    without_tags = _TAG.sub("", raw or "")
    return re.sub(r"\s+", " ", html_module.unescape(without_tags)).strip()


def parse_items(body: str, limit: int) -> list[SearchResult]:
    """Extract articles from the RSS feed.

    The item's ``<link>`` is a ``news.google.com`` redirect, which is what the
    feed publishes; the *publisher* comes from the ``<source url=…>`` element. The
    publisher is recorded as the display URL so the operator sees where an article
    is from rather than a long opaque redirect.
    """
    results: list[SearchResult] = []
    for match in _ITEM.finditer(body or ""):
        item = match.group("body")

        title_match = _TITLE.search(item)
        title = _clean(title_match.group("text")) if title_match else ""
        if not title:
            continue

        link_match = _LINK.search(item)
        url = _clean(link_match.group("text")) if link_match else ""
        if not url:
            continue

        source_match = _SOURCE.search(item)
        publisher = _clean(source_match.group("name")) if source_match else ""
        publisher_url = (source_match.group("url") if source_match else "").strip()

        date_match = _PUB_DATE.search(item)
        published = _clean(date_match.group("text")) if date_match else ""

        # The feed's title already carries "- Publisher"; the publisher is kept
        # separately as well because it is the useful part for judging a source.
        snippet = " · ".join(
            part for part in (publisher, published) if part
        ) or "News article"

        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippet,
                display_url=publisher_url or publisher,
            )
        )
        if len(results) >= limit:
            break
    return results


def google_news(query: str, *, limit: int, timeout: int) -> SearchResponse:
    """Run one query against the Google News RSS feed."""
    cleaned = re.sub(r"\s+", " ", (query or "").strip())[:MAX_QUERY_LENGTH]
    if not cleaned:
        return SearchResponse(query="", ok=False, error="Empty query.")

    url = f"{ENDPOINT}?" + urllib.parse.urlencode(
        {"q": cleaned, "hl": "en-US", "gl": "US", "ceid": "US:en"}
    )
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml,application/xml,text/xml",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return SearchResponse(
            query=cleaned,
            ok=False,
            error=f"{PROVIDER_LABEL} refused the request (HTTP {exc.code})",
        )
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        logger.warning("%s failed for %r: %s", PROVIDER_LABEL, cleaned, exc)
        return SearchResponse(
            query=cleaned, ok=False, error=f"{PROVIDER_LABEL}: {type(exc).__name__}: {exc}"
        )

    if looks_blocked(raw):
        return SearchResponse(
            query=cleaned, ok=False, error=f"{PROVIDER_LABEL} served a challenge page"
        )

    results = parse_items(raw, limit)
    if not results:
        return SearchResponse(
            query=cleaned,
            ok=False,
            error=(
                f"{PROVIDER_LABEL} answered but no articles could be parsed — this "
                "usually means the query found no coverage rather than a fault"
            ),
        )

    response = SearchResponse(query=cleaned, results=results)
    response.provider = PROVIDER_NAME
    response.provider_label = PROVIDER_LABEL
    return response
