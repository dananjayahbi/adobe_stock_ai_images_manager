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
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

#: The front-end that actually answers a scripted request.
SEARCH_ENDPOINT = "https://lite.duckduckgo.com/lite/"

#: Provider identity, recorded on every response so the UI can name the source.
PROVIDER_NAME = "duckduckgo"
PROVIDER_LABEL = "DuckDuckGo"

#: **Evidence tiers.** This is the load-bearing distinction for the provider chain.
#:
#: A general web index answers "what exists and who writes about it" with the same
#: *kind* of evidence whatever index it is, so falling back from one general index
#: to another is **silent** — the operator's conclusions are unaffected. Editorial
#: coverage is a different tier: it shows what is being written about a topic, not
#: how many competing stock images exist, so a result from that tier degrades the
#: evidence and has to be announced.
#:
#: Before this existed there was a single ``used_fallback`` flag, which meant a
#: Brave-to-DuckDuckGo fallback would have been labelled "news and editorial
#: coverage" — a false statement about perfectly good general-index results.
TIER_GENERAL_INDEX = "general_index"
TIER_EDITORIAL = "editorial"


@dataclass(frozen=True)
class Provider:
    """One entry in the fallback chain.

    ``run`` is called as ``run(query, limit=…, timeout=…)``. Bound as a closure
    rather than passed the settings, so :func:`provider_chain` is the single place
    that reads configuration and a provider cannot pick up a different key than
    the one the chain was built with.
    """

    name: str
    label: str
    tier: str
    run: Callable[..., "SearchResponse"]
    #: True when the provider is useless without an operator-supplied credential.
    requires_key: bool = False

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
    #: True when the answer came from anywhere other than the first provider in
    #: the chain. On its own this says nothing about quality — see
    #: :attr:`degraded_source`.
    used_fallback: bool = False
    #: True when the answer came from a **lower evidence tier** than the primary
    #: provider (editorial coverage rather than a general web index). Only this
    #: warrants the caveat in :meth:`to_tool_text`; a same-tier fallback is silent
    #: by design.
    degraded_source: bool = False
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
        if self.degraded_source:
            payload["degraded_source"] = True
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

        # The caveat is keyed on the evidence TIER, not on "a fallback happened".
        # A same-tier fallback (Brave to DuckDuckGo) returns the same kind of
        # evidence and needs no warning; editorial coverage is a weaker kind and
        # does, because it cannot show how many competing stock images exist.
        source_note = ""
        if self.degraded_source:
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


def clean_fragment(raw: str) -> str:
    """Collapse whitespace and unescape entities in a text fragment.

    Public because every provider needs it and each one used to carry its own
    near-identical copy — three implementations of the same rule is three places
    for it to drift. Markup is *not* stripped here: a JSON provider's text is
    already plain, and stripping tags from a legitimate `<` would corrupt it.
    """
    return re.sub(r"\s+", " ", html_module.unescape(raw or "")).strip()


def _clean(raw: str) -> str:
    """Strip tags *and* entities from a fragment of scraped markup."""
    without_tags = _TAG.sub(" ", raw or "")
    return clean_fragment(without_tags)


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


def _brave_provider(api_key: str) -> Provider:
    """Brave, bound to the operator's key.

    The key is captured in the closure so the chain is fully decided before any
    search runs: a settings change mid-run cannot switch providers part-way
    through a conversation.
    """
    from services.research import brave

    def _run(query: str, *, limit: int, timeout: int) -> SearchResponse:
        return brave.brave_search(query, api_key=api_key, limit=limit, timeout=timeout)

    return Provider(
        name=brave.PROVIDER_NAME,
        label=brave.PROVIDER_LABEL,
        tier=TIER_GENERAL_INDEX,
        run=_run,
        requires_key=True,
    )


def _duckduckgo_provider() -> Provider:
    return Provider(
        name=PROVIDER_NAME,
        label=PROVIDER_LABEL,
        tier=TIER_GENERAL_INDEX,
        run=_duckduckgo,
    )


def _news_provider() -> Provider:
    """Google News RSS — a *lower tier*, so its use is announced."""
    from services.research import news_search

    return Provider(
        name=news_search.PROVIDER_NAME,
        label=news_search.PROVIDER_LABEL,
        tier=TIER_EDITORIAL,
        run=news_search.google_news,
    )


def provider_chain(
    *, brave_api_key: str = "", use_brave: bool = False
) -> list[Provider]:
    """The providers to try, in order.

    The operator's settings decide the order; nothing here is hard-coded to a
    provider, so enabling Brave in Settings changes *where the agent looks* with
    no code change and no restart.

    * **Brave enabled and keyed** → Brave first. It is the default search.
    * Otherwise → DuckDuckGo first, so a run is byte-identical to before the
      feature existed when Brave is off.
    * Google News is always last, because it is the only provider that cannot
      answer "how much supply exists" — it is the last resort, not a peer.
    """
    chain: list[Provider] = []
    if use_brave and (brave_api_key or "").strip():
        chain.append(_brave_provider(brave_api_key))
    chain.append(_duckduckgo_provider())
    chain.append(_news_provider())
    return chain


def search(
    query: str,
    *,
    limit: int = MAX_RESULTS,
    timeout: int = 25,
    brave_api_key: str = "",
    use_brave: bool = False,
) -> SearchResponse:
    """Run one web search, falling back through the provider chain, then reporting.

    **Never raises for a provider problem.** Every provider's failure is collected
    and, if all fail, returned as ``ok=False`` with each provider's own message, so
    the agent loop can record the step, tell the model what happened, and continue.
    A hard exception would abort a run that could still produce a useful answer.

    A fallback within the same evidence tier is **silent** — the results are the
    same kind of evidence, so flagging them would be a false alarm. A fallback to a
    lower tier (editorial coverage) is marked ``degraded_source`` so the tool text
    can warn the agent not to read it as catalogue data.
    """
    cleaned = re.sub(r"\s+", " ", (query or "").strip())[:MAX_QUERY_LENGTH]
    if not cleaned:
        return SearchResponse(query="", ok=False, error="Empty query.")

    chain = provider_chain(brave_api_key=brave_api_key, use_brave=use_brave)
    primary_tier = chain[0].tier

    attempts: list[str] = []
    for index, provider in enumerate(chain):
        outcome = provider.run(cleaned, limit=limit, timeout=timeout)
        if outcome.ok and outcome.results:
            outcome.used_fallback = index > 0
            outcome.degraded_source = provider.tier != primary_tier
            return outcome
        attempts.append(f"{outcome.provider_label or provider.label}: {outcome.error}")

    return SearchResponse(
        query=cleaned,
        ok=False,
        error="every search provider failed",
        provider_errors=attempts,
    )


def run_search(
    query: str,
    *,
    limit: int = MAX_RESULTS,
    timeout: int = 25,
    search_config: "SearchConfigLike | None" = None,
) -> SearchResponse:
    """Run a search using the operator's **saved** provider settings.

    This is what the tools call, so a research run picks up a provider change made
    in Settings with no restart — the same contract :func:`app_settings.resolve`
    gives the LLM endpoint.

    Settings are read here (once, at the top of the call) rather than inside the
    provider chain so the configuration is resolved exactly once per search and the
    pure :func:`search` function stays trivially testable with an explicit chain.

    The import is function-local because ``services.app_settings`` is a
    *application-level* module and ``services.research`` is a feature package;
    importing it at module scope would make this package unimportable on its own,
    which the research tests rely on.
    """
    from services import app_settings

    config = search_config if search_config is not None else app_settings.resolve_search()
    if config.uses_brave:
        _pace_brave(config.rate_limit_per_second)
    return search(
        query,
        limit=limit,
        timeout=timeout,
        brave_api_key=config.api_key,
        use_brave=config.uses_brave,
    )


#: When the last Brave request was sent. Used to space requests out to the plan's
#: allowed rate, which is the difference between a clean run and one that trips a
#: 429 on the second of three queries.
_last_brave_call = 0.0


def _pace_brave(rate_limit_per_second: float) -> None:
    """Sleep just long enough to stay inside the plan's request rate.

    Pacing here rather than in the caller because a single ``market_overview`` call
    fires **three** queries back to back: at Brave's free-plan rate of one per
    second, queries two and three would otherwise be rejected, and the run would
    silently fall through to the next provider while *appearing* to have used
    Brave. Doing it once, on the path every search takes, means no caller has to
    know the plan's rate.

    Deliberately sleeps only the shortfall, so a naturally slow run is never
    slowed further. Not a substitute for the fallback chain: a rate limit can still
    be hit by other clients on the same key, which is why the chain exists.
    """
    global _last_brave_call

    if rate_limit_per_second <= 0:
        return
    minimum_gap = 1.0 / rate_limit_per_second
    elapsed = time.monotonic() - _last_brave_call
    if _last_brave_call and elapsed < minimum_gap:
        time.sleep(minimum_gap - elapsed)
    _last_brave_call = time.monotonic()


#: Structural type for the config :func:`run_search` accepts. Declared as a
#: ``Protocol``-shaped alias rather than an import so this module never depends on
#: ``app_settings`` at import time.
SearchConfigLike = "app_settings.SearchConfig"
