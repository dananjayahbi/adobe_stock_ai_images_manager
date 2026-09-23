"""Web search for the research agent — no API key, standard library only.

Why this module exists
----------------------
The research modes need the agent to read what real people write about a niche
(customer demand, what already floods the market, whether a concept is
over-supplied). That means actual web results, not model recall.

Why it is written the way it is
-------------------------------
DuckDuckGo has **two** HTML front-ends and only one of them answers a script:

* ``GET https://html.duckduckgo.com/html/?q=…`` now returns **HTTP 202** with an
  anti-bot interstitial ("Select all squares containing a duck"). It does this
  for a plain GET, for a GET with a region hint, and for a POST to the same
  path. Verified from this machine on 2026-09-23.
* ``POST https://lite.duckduckgo.com/lite/`` with a form-encoded ``q`` answers
  **HTTP 200** with real results.

The failure mode matters more than the fix: a blocked search returns a *200-ish
page with no results*, which is indistinguishable from "the web has nothing to
say about this". Reporting that as "no results" would let the agent conclude a
niche is unserved when it simply could not look. So a block is detected
explicitly and raised as :class:`SearchBlocked`, and the caller is required to
say so out loud rather than silently treat it as an empty result set.

Parsing is regex-based on purpose: the repository's backend deliberately carries
no HTML parser dependency (see ``requirements.txt``), and the lite markup is a
stable, tiny table with three class names.
"""

from __future__ import annotations

import html as html_module
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

#: The front-end that actually answers a scripted request.
SEARCH_ENDPOINT = "https://lite.duckduckgo.com/lite/"

#: Provider identity, recorded on every response so the UI can name the source.
PROVIDER_NAME = "duckduckgo"
PROVIDER_LABEL = "DuckDuckGo"

#: A browser UA. The default ``Python-urllib/3.x`` UA is rejected outright.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

#: Markers of DuckDuckGo's anti-bot interstitial. Checked before parsing, so a
#: challenge page can never be mistaken for a page with zero results.
_BLOCK_MARKERS = (
    "anomaly-modal",
    "bots use duckduckgo",
    "unfortunately, bots",
    "challenge to confirm",
)

#: Longest query accepted; DuckDuckGo truncates far earlier and a runaway
#: query usually means the model looped.
MAX_QUERY_LENGTH = 300

#: Results returned per search. The agent reads snippets, so a handful of
#: well-ranked hits beats a long tail.
MAX_RESULTS = 8

#: Cap on a single response body, so a hostile or broken response cannot
#: exhaust memory.
MAX_BODY_BYTES = 2_000_000

#: The lite front-end writes class attributes with **single** quotes
#: (``class='result-link'``), unlike the html front-end which uses double
#: quotes. Both are accepted so a markup change does not silently yield zero
#: results.
_QUOTE = r"['\"]"

RESULT_LINK = re.compile(
    rf"<a\b[^>]*href={_QUOTE}(?P<href>[^'\"]+){_QUOTE}[^>]*class={_QUOTE}[^'\"]*result-link[^'\"]*{_QUOTE}[^>]*>(?P<title>.*?)</a>",
    re.S | re.I,
)
#: Some builds put the class before the href; matched separately so the order
#: of attributes in the markup is not a correctness dependency.
RESULT_LINK_REVERSED = re.compile(
    rf"<a\b[^>]*class={_QUOTE}[^'\"]*result-link[^'\"]*{_QUOTE}[^>]*href={_QUOTE}(?P<href>[^'\"]+){_QUOTE}[^>]*>(?P<title>.*?)</a>",
    re.S | re.I,
)
RESULT_SNIPPET = re.compile(
    rf"<td\b[^>]*class={_QUOTE}[^'\"]*result-snippet[^'\"]*{_QUOTE}[^>]*>(?P<text>.*?)</td>",
    re.S | re.I,
)
DISPLAY_URL = re.compile(
    rf"<span\b[^>]*class={_QUOTE}[^'\"]*link-text[^'\"]*{_QUOTE}[^>]*>(?P<text>.*?)</span>",
    re.S | re.I,
)
_TAG = re.compile(r"<[^>]+>")


class SearchError(RuntimeError):
    """Base class for a search that could not be completed."""


class SearchBlocked(SearchError):
    """The search provider served an anti-bot challenge instead of results.

    Raised rather than returning an empty list: "the provider refused to
    answer" and "there is nothing to find" are different facts, and the agent's
    conclusion depends on which one is true.
    """


class SearchUnavailable(SearchError):
    """The search provider could not be reached at all."""


@dataclass(frozen=True)
class SearchResult:
    """One organic result."""

    title: str
    url: str
    snippet: str = ""
    display_url: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "display_url": self.display_url or self.url,
        }


@dataclass
class SearchResponse:
    """The outcome of one search, including how much to trust it."""

    query: str
    results: list[SearchResult] = field(default_factory=list)
    #: True when the provider answered with real results.
    ok: bool = True
    #: Populated when ``ok`` is False — always surfaced to the model, never
    #: silently swallowed.
    error: str = ""
    #: Which provider produced the results, and whether a fallback was needed.
    #: Recorded so the UI can say where a result came from, and so a run that only
    #: succeeded on the second provider is visibly degraded rather than looking
    #: identical to a clean one.
    provider: str = ""
    provider_label: str = ""
    used_fallback: bool = False
    #: What every provider said when they all failed, so the operator can tell
    #: "rate-limited" apart from "no network".
    provider_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload: dict = {
            "query": self.query,
            "ok": self.ok,
            "count": len(self.results),
            "results": [result.to_dict() for result in self.results],
        }
        if self.provider:
            payload["provider"] = self.provider
        if self.used_fallback:
            payload["used_fallback"] = True
        if self.error:
            payload["error"] = self.error
        return payload

    def to_tool_text(self) -> str:
        """Render for the model, keeping failure distinguishable from emptiness."""
        if not self.ok:
            details = ""
            if self.provider_errors:
                details = "\nWhat each provider said:\n" + "\n".join(
                    f"- {entry}" for entry in self.provider_errors
                )
            return (
                f"SEARCH FAILED for query {self.query!r}: {self.error}{details}\n"
                "Do NOT conclude that the niche has no competition or no demand. "
                "The search simply could not be completed — say so in your answer "
                "and lower your confidence accordingly."
            )
        if not self.results:
            return (
                f"Search returned 0 results for {self.query!r}. This may mean the "
                "query was too narrow rather than that nothing exists; try a "
                "broader phrasing before drawing a conclusion."
            )

        source_note = ""
        if self.used_fallback:
            source_note = (
                f"\n(Note: the primary search provider was unavailable, so these "
                f"results come from {self.provider_label}. They are news and "
                f"editorial coverage, which shows what is being written about the "
                f"topic — not how many competing stock images exist.)"
            )

        lines = [
            f"Search results for {self.query!r} ({len(self.results)} hits"
            + (f", via {self.provider_label}" if self.provider_label else "")
            + "):"
        ]
        for index, result in enumerate(self.results, start=1):
            lines.append(f"{index}. {result.title}")
            lines.append(f"   URL: {result.url}")
            if result.snippet:
                lines.append(f"   {result.snippet}")
        if source_note:
            lines.append(source_note)
        return "\n".join(lines)


def _clean(raw: str) -> str:
    """Strip tags and entities from a fragment of markup."""
    without_tags = _TAG.sub(" ", raw or "")
    collapsed = re.sub(r"\s+", " ", html_module.unescape(without_tags))
    return collapsed.strip()


def _unwrap(href: str) -> str:
    """Turn a DuckDuckGo redirect into the destination URL.

    The html front-end wraps every link in ``/l/…?uddg=<encoded>``; the lite
    front-end usually emits the destination directly but falls back to the
    wrapper. Handling both keeps the URLs the agent cites readable.
    """
    if "uddg=" in href:
        encoded = href.split("uddg=", 1)[1].split("&", 1)[0]
        return urllib.parse.unquote(encoded)
    return href


def looks_blocked(body: str) -> bool:
    """Whether a response is the anti-bot interstitial rather than results."""
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _BLOCK_MARKERS)


def parse_results(body: str, limit: int = MAX_RESULTS) -> list[SearchResult]:
    """Extract organic results from the lite front-end's markup.

    Titles and snippets are paired **by position**, because the lite markup is
    a flat sequence of rows rather than nested result containers. A snippet
    count mismatch therefore degrades to an empty snippet for the tail rather
    than mis-attributing one result's snippet to another.
    """
    matches = list(RESULT_LINK.finditer(body))
    if not matches:
        matches = list(RESULT_LINK_REVERSED.finditer(body))

    snippets = [_clean(match.group("text")) for match in RESULT_SNIPPET.finditer(body)]
    display_urls = [_clean(match.group("text")) for match in DISPLAY_URL.finditer(body)]

    results: list[SearchResult] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        url = _unwrap(match.group("href")).strip()
        title = _clean(match.group("title"))
        if not url or not title:
            continue
        # The lite page repeats the top hit as an ad-style block; identical
        # destinations are collapsed so the agent does not read one source
        # twice and count it as corroboration.
        if url in seen:
            continue
        seen.add(url)
        results.append(
            SearchResult(
                title=title,
                url=url,
                snippet=snippets[index] if index < len(snippets) else "",
                display_url=display_urls[index] if index < len(display_urls) else "",
            )
        )
        if len(results) >= limit:
            break
    return results


def _duckduckgo(query: str, *, limit: int, timeout: int) -> SearchResponse:
    """Query DuckDuckGo's lite front-end — the primary provider.

    Kept as a named function (rather than inlined into :func:`search`) so the
    orchestrator can be tested against a stubbed provider with no network call.
    """
    body = urllib.parse.urlencode({"q": query}).encode()
    request = urllib.request.Request(
        SEARCH_ENDPOINT,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_BODY_BYTES).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code in (202, 403, 429):
            return SearchResponse(
                query=query,
                ok=False,
                error=(
                    f"the search provider refused the request (HTTP {exc.code}), "
                    "which is its anti-bot challenge"
                ),
            )
        return SearchResponse(query=query, ok=False, error=f"HTTP {exc.code}")
    except Exception as exc:  # noqa: BLE001 - every failure becomes a reported step
        logger.warning("Search failed for %r: %s", query, exc)
        return SearchResponse(query=query, ok=False, error=f"{type(exc).__name__}: {exc}")

    if looks_blocked(raw):
        return SearchResponse(
            query=query,
            ok=False,
            error=(
                "the search provider served an anti-bot challenge page instead of "
                "results"
            ),
        )

    results = parse_results(raw, limit=limit)
    if not results:
        # A 200 with no parseable results is usually a markup change rather than a
        # genuinely empty result set, and the two demand different reactions, so it
        # is reported as a degraded (not empty) search.
        return SearchResponse(
            query=query,
            ok=False,
            error="the provider answered but no results could be parsed from the page",
        )

    response = SearchResponse(query=query, results=results)
    response.provider = PROVIDER_NAME
    response.provider_label = PROVIDER_LABEL
    return response


def search(query: str, *, limit: int = MAX_RESULTS, timeout: int = 25) -> SearchResponse:
    """Run one web search, falling back to a second provider, then reporting.

    Provider order matters: DuckDuckGo's general index answers a query about
    *anything* well, so it is tried first; the news feed is the fallback, because
    it is editorial coverage rather than a general index.

    **Never raises for a provider problem.** Every provider's failure is collected
    and, if all fail, returned as ``ok=False`` with each provider's own message, so
    the agent loop can record the step, tell the model what happened, and continue.
    A hard exception would abort a run that could still produce a useful answer.
    """
    cleaned = re.sub(r"\s+", " ", (query or "").strip())[:MAX_QUERY_LENGTH]
    if not cleaned:
        return SearchResponse(query="", ok=False, error="Empty query.")

    # Imported here rather than at module scope: the news provider imports this
    # module's shared helpers, so a top-level import would be circular.
    from services.research import news_search

    attempts: list[str] = []
    for index, provider in enumerate((_duckduckgo, news_search.google_news)):
        outcome = provider(cleaned, limit=limit, timeout=timeout)
        if outcome.ok and outcome.results:
            outcome.used_fallback = index > 0
            return outcome
        attempts.append(
            f"{outcome.provider_label or provider.__name__}: {outcome.error}"
        )

    return SearchResponse(
        query=cleaned,
        ok=False,
        error="every search provider failed",
        provider_errors=attempts,
    )
