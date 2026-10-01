"""Brave Search provider and the tiered provider chain.

The behaviour under test is the *fallback contract*, which is easy to get subtly
wrong in a way nothing else notices:

* A fallback **within** the general-index tier (Brave → DuckDuckGo) must be
  **silent**. Both return the same kind of evidence, so a caveat would be a false
  statement about good results.
* A fallback **to a lower tier** (→ Google News) must be announced, because
  editorial coverage cannot show how many competing stock images exist.

A single ``used_fallback`` flag cannot express that distinction, which is why
``degraded_source`` exists and why it is asserted from both sides here.
"""

from __future__ import annotations

import gzip
import json

import pytest

from services.research import brave, news_search
from services.research import search as search_module


# --------------------------------------------------------------------------- #
# Payload parsing — pure, so it is tested against a captured shape
# --------------------------------------------------------------------------- #

def test_the_web_results_shape_is_parsed():
    payload = {
        "web": {
            "results": [
                {
                    "title": "Cold storage warehouse robots",
                    "url": "https://example.com/a",
                    "description": "A guide to automated cold storage.",
                    "profile": {"long_name": "Example"},
                }
            ]
        }
    }
    results = brave.parse_payload(payload, limit=5)
    assert len(results) == 1
    assert results[0].title == "Cold storage warehouse robots"
    assert results[0].url == "https://example.com/a"
    assert "automated cold storage" in results[0].snippet
    # The publisher is the useful part for judging a source, so it is displayed
    # rather than the bare URL — the same convention the news provider uses.
    assert results[0].display_url == "Example"


def test_extra_snippets_are_folded_in_but_bounded():
    payload = {
        "web": {
            "results": [
                {
                    "title": "T",
                    "url": "https://example.com/a",
                    "description": "first",
                    "extra_snippets": ["second", "third", "fourth", "fifth"],
                }
            ]
        }
    }
    results = brave.parse_payload(payload, limit=5)
    snippet = results[0].snippet
    assert "first" in snippet
    assert "second" in snippet
    assert "third" in snippet
    # Bounded: one result must not dominate the tool output.
    assert "fifth" not in snippet


def test_the_limit_is_respected():
    payload = {
        "web": {
            "results": [
                {"title": f"T{index}", "url": f"https://example.com/{index}"}
                for index in range(10)
            ]
        }
    }
    assert len(brave.parse_payload(payload, limit=3)) == 3


def test_a_result_without_a_url_is_skipped_not_emitted_empty():
    payload = {
        "web": {
            "results": [
                {"title": "No URL"},
                {"url": "https://example.com/ok", "title": "Has URL"},
            ]
        }
    }
    results = brave.parse_payload(payload, limit=5)
    assert len(results) == 1
    assert results[0].url == "https://example.com/ok"


def test_a_payload_with_no_web_key_is_not_an_exception():
    assert brave.parse_payload({}, limit=5) == []
    assert brave.parse_payload({"web": {}}, limit=5) == []
    assert brave.parse_payload({"web": {"results": None}}, limit=5) == []


# --------------------------------------------------------------------------- #
# HTTP failure handling
# --------------------------------------------------------------------------- #

def test_a_missing_key_is_reported_rather_than_skipped(monkeypatch):
    """A configuration fault must be visible, not look like a dead provider."""
    response = brave.brave_search("x", api_key="", limit=5, timeout=5)
    assert response.ok is False
    assert "no API key is configured" in response.error


def test_a_rate_limit_names_the_condition(monkeypatch):
    """'rate-limited' and 'bad key' need different operator reactions."""
    message = brave._describe_http_error(
        429, json.dumps({"error": {"code": "RATE_LIMITED", "detail": "quota"}})
    )
    assert "429" in message
    assert "rate limit" in message


def test_a_rejected_key_says_to_check_the_key():
    message = brave._describe_http_error(401, "")
    assert "401" in message
    assert "API key was rejected" in message


def test_a_rejected_query_is_distinguished_from_a_key_problem():
    message = brave._describe_http_error(422, "")
    assert "invalid" in message
    assert "key" not in message


def test_an_http_error_becomes_an_ok_false_response(monkeypatch):
    """Never raises: the orchestrator needs to fall through to the next provider."""
    import urllib.error

    def _raise(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise urllib.error.HTTPError(
            brave.ENDPOINT, 429, "Too Many Requests", {}, None  # type: ignore[arg-type]
        )

    monkeypatch.setattr(brave.urllib.request, "urlopen", _raise)
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is False
    assert "429" in response.error


def test_a_network_failure_becomes_an_ok_false_response(monkeypatch):
    def _raise(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise TimeoutError("timed out")

    monkeypatch.setattr(brave.urllib.request, "urlopen", _raise)
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is False
    assert "TimeoutError" in response.error


def test_a_successful_response_is_labelled_with_its_provider(monkeypatch):
    body = json.dumps(
        {"web": {"results": [{"title": "T", "url": "https://example.com/a"}]}}
    )

    class _Response:
        headers: dict = {}

        def read(self, _n=None):  # noqa: ANN001
            return body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    monkeypatch.setattr(brave.urllib.request, "urlopen", lambda *a, **k: _Response())
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is True
    assert response.provider == brave.PROVIDER_NAME
    assert response.provider_label == brave.PROVIDER_LABEL
    assert len(response.results) == 1


def test_a_gzipped_response_is_decompressed(monkeypatch):
    """urllib does not decompress for us, and Brave documents gzip.

    Without this the body decodes to binary noise and a *successful* response
    looks like a provider that returned no results — a silent, misleading failure.
    """
    body = json.dumps(
        {"web": {"results": [{"title": "Zipped", "url": "https://example.com/z"}]}}
    )

    class _Response:
        headers = {"Content-Encoding": "gzip"}

        def read(self, _n=None):  # noqa: ANN001
            return gzip.compress(body.encode())

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    monkeypatch.setattr(brave.urllib.request, "urlopen", lambda *a, **k: _Response())
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is True
    assert response.results[0].title == "Zipped"


def test_a_non_json_body_is_reported_not_raised(monkeypatch):
    class _Response:
        headers: dict = {}

        def read(self, _n=None):  # noqa: ANN001
            return b"<html>not json</html>"

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    monkeypatch.setattr(brave.urllib.request, "urlopen", lambda *a, **k: _Response())
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is False
    assert "not JSON" in response.error


def test_an_empty_result_set_is_reported_as_degraded_not_empty(monkeypatch):
    """"The provider answered but produced nothing readable" is not "nothing exists"."""
    class _Response:
        headers: dict = {}

        def read(self, _n=None):  # noqa: ANN001
            return json.dumps({"web": {"results": []}}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    monkeypatch.setattr(brave.urllib.request, "urlopen", lambda *a, **k: _Response())
    response = brave.brave_search("x", api_key="k", limit=5, timeout=5)
    assert response.ok is False
    assert "no readable web results" in response.error


# --------------------------------------------------------------------------- #
# The provider chain
# --------------------------------------------------------------------------- #

def test_brave_is_off_by_default_so_a_run_is_unchanged():
    """With no key the chain must be byte-identical to before the feature existed."""
    names = [provider.name for provider in search_module.provider_chain()]
    assert names == ["duckduckgo", "google_news"]


def test_enabling_brave_puts_it_first():
    names = [
        provider.name
        for provider in search_module.provider_chain(
            brave_api_key="k", use_brave=True
        )
    ]
    assert names[0] == "brave"


def test_an_enabled_provider_without_a_key_is_not_used():
    """'Enabled' and 'usable' are different states, and only the second matters."""
    names = [
        provider.name
        for provider in search_module.provider_chain(brave_api_key="", use_brave=True)
    ]
    assert "brave" not in names


def test_the_news_provider_is_always_last():
    """It is the only provider that cannot answer 'how much supply exists'."""
    for kwargs in ({}, {"brave_api_key": "k", "use_brave": True}):
        chain = search_module.provider_chain(**kwargs)
        assert chain[-1].name == news_search.PROVIDER_NAME
        assert chain[-1].tier == search_module.TIER_EDITORIAL


def test_the_general_index_providers_share_a_tier():
    """Same tier is what makes the Brave-to-DuckDuckGo fallback silent."""
    chain = search_module.provider_chain(brave_api_key="k", use_brave=True)
    tiers = {provider.name: provider.tier for provider in chain}
    assert tiers["brave"] == search_module.TIER_GENERAL_INDEX
    assert tiers["duckduckgo"] == search_module.TIER_GENERAL_INDEX


# --------------------------------------------------------------------------- #
# Fallback semantics — the load-bearing part
# --------------------------------------------------------------------------- #

def _stub(monkeypatch, **providers):
    """Replace each named provider's runner with a scripted response.

    Rebuilds the chain rather than mutating it: :class:`Provider` is frozen, and
    a test that reached into a frozen dataclass would be testing its own
    monkeypatch rather than the orchestrator.

    The runner is built by a *named function* rather than an inline lambda inside
    the comprehension. A lambda there would close over the loop variable, so every
    provider would run the **last** entry's script — the classic late-binding trap,
    and it would make these tests pass or fail for a reason unrelated to the
    fallback logic they exist to check.
    """

    def _runner_for(entry, scripted):
        def _run(query, **kwargs):  # noqa: ANN001, ANN003, ARG001
            return scripted

        return _run

    real_chain = search_module.provider_chain(brave_api_key="k", use_brave=True)

    def _chain(**kwargs):  # noqa: ANN003, ARG001
        return [
            search_module.Provider(
                name=entry.name,
                label=entry.label,
                tier=entry.tier,
                run=(
                    _runner_for(entry, providers[entry.name])
                    if entry.name in providers
                    else entry.run
                ),
            )
            for entry in real_chain
        ]

    monkeypatch.setattr(search_module, "provider_chain", _chain)


def _ok(label: str, title: str = "Result", url: str = "https://example.com/a"):
    return search_module.SearchResponse(
        query="q",
        results=[search_module.SearchResult(title=title, url=url)],
        provider=label.lower().replace(" ", "_"),
        provider_label=label,
    )


def _fail(label: str, error: str = "refused"):
    return search_module.SearchResponse(
        query="q", ok=False, error=error, provider_label=label
    )


def test_brave_is_used_when_it_works(monkeypatch):
    _stub(monkeypatch, brave=_ok("Brave Search", "From Brave"))
    response = search_module.search("x", brave_api_key="k", use_brave=True)
    assert response.results[0].title == "From Brave"
    assert response.used_fallback is False
    assert response.degraded_source is False


def test_falling_back_to_duckduckgo_is_silent(monkeypatch):
    """The whole point of the tier distinction.

    Brave failing over to DuckDuckGo is a change of vendor, not of evidence
    quality. A single ``used_fallback`` flag would have labelled these perfectly
    good general-index results as "news and editorial coverage".
    """
    _stub(
        monkeypatch,
        brave=_fail("Brave Search", "HTTP 429"),
        duckduckgo=_ok("DuckDuckGo", "From DDG"),
    )
    response = search_module.search("x", brave_api_key="k", use_brave=True)
    assert response.ok is True
    assert response.results[0].title == "From DDG"
    # A fallback DID happen...
    assert response.used_fallback is True
    # ...but it is not a degraded source, so no caveat is emitted.
    assert response.degraded_source is False
    text = response.to_tool_text()
    assert "news and" not in text
    assert "editorial" not in text


def test_falling_back_to_news_is_announced(monkeypatch):
    _stub(
        monkeypatch,
        brave=_fail("Brave Search", "HTTP 429"),
        duckduckgo=_fail("DuckDuckGo", "anti-bot challenge"),
        google_news=_ok("Google News", "An article"),
    )
    response = search_module.search("x", brave_api_key="k", use_brave=True)
    assert response.ok is True
    assert response.degraded_source is True
    assert "news and" in response.to_tool_text()


def test_the_rate_limit_falls_through_to_the_next_provider(monkeypatch):
    """The user-facing requirement: an exceeded limit must not end the search."""
    _stub(
        monkeypatch,
        brave=_fail("Brave Search", "the plan's request rate limit was exceeded"),
        duckduckgo=_ok("DuckDuckGo", "Still works"),
    )
    response = search_module.search("x", brave_api_key="k", use_brave=True)
    assert response.ok is True
    assert response.results[0].title == "Still works"


def test_every_provider_failing_lists_each_one(monkeypatch):
    _stub(
        monkeypatch,
        brave=_fail("Brave Search", "HTTP 401"),
        duckduckgo=_fail("DuckDuckGo", "anti-bot challenge"),
        google_news=_fail("Google News", "HTTP 503"),
    )
    response = search_module.search("x", brave_api_key="k", use_brave=True)
    assert response.ok is False
    assert "every search provider failed" in response.error
    assert len(response.provider_errors) == 3
    assert any("401" in entry for entry in response.provider_errors)
    assert "Do NOT conclude" in response.to_tool_text()


def test_a_disabled_brave_never_calls_brave(monkeypatch):
    """With the setting off the run must be unchanged, not merely unlabelled."""
    called = {"brave": False}

    def _explode(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        called["brave"] = True
        raise AssertionError("Brave must not be called when it is disabled")

    monkeypatch.setattr(brave, "brave_search", _explode)
    monkeypatch.setattr(
        search_module,
        "_duckduckgo",
        lambda query, **kwargs: _ok("DuckDuckGo"),
    )
    response = search_module.search("x", brave_api_key="k", use_brave=False)
    assert response.ok is True
    assert called["brave"] is False


@pytest.mark.parametrize("count", [1, 5, 20, 50])
def test_the_requested_count_is_clamped_to_the_api_maximum(count):
    """Brave rejects ``count`` above 20 with a 422, so it must never be sent."""
    assert max(1, min(count, brave.MAX_COUNT)) <= brave.MAX_COUNT


# --------------------------------------------------------------------------- #
# Pacing — one market_overview call fires three queries back to back
# --------------------------------------------------------------------------- #

def test_pacing_sleeps_only_the_shortfall(monkeypatch):
    """A naturally slow run must not be slowed further."""
    slept: list[float] = []
    clock = {"now": 100.0}

    monkeypatch.setattr(search_module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search_module.time, "sleep", lambda seconds: slept.append(seconds))
    # Reset the module's cross-call memory so the test is order-independent.
    monkeypatch.setattr(search_module, "_last_brave_call", 0.0)

    # First call: nothing to wait for.
    search_module._pace_brave(1.0)
    assert slept == []

    # Second call immediately after: the full gap is missing.
    search_module._pace_brave(1.0)
    assert slept == [pytest.approx(1.0, abs=0.05)]


def test_pacing_does_not_sleep_when_enough_time_has_passed(monkeypatch):
    slept: list[float] = []
    clock = {"now": 100.0}

    monkeypatch.setattr(search_module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search_module.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(search_module, "_last_brave_call", 0.0)

    search_module._pace_brave(1.0)
    clock["now"] += 5.0  # a slow search already covered the gap
    search_module._pace_brave(1.0)
    assert slept == []


def test_a_faster_plan_paces_less(monkeypatch):
    slept: list[float] = []
    clock = {"now": 100.0}

    monkeypatch.setattr(search_module.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(search_module.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(search_module, "_last_brave_call", 0.0)

    search_module._pace_brave(4.0)
    search_module._pace_brave(4.0)
    # 4 requests/second means a quarter-second gap.
    assert slept == [pytest.approx(0.25, abs=0.02)]


def test_a_zero_rate_disables_pacing(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(search_module.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(search_module, "_last_brave_call", 0.0)
    search_module._pace_brave(0)
    assert slept == []


def test_pacing_is_skipped_entirely_when_brave_is_off(monkeypatch):
    """Pacing must not add latency to a run that never calls Brave."""
    from services import app_settings

    slept: list[float] = []
    monkeypatch.setattr(search_module.time, "sleep", lambda seconds: slept.append(seconds))
    monkeypatch.setattr(search_module, "search", lambda *a, **k: _ok("DuckDuckGo"))
    monkeypatch.setattr(
        app_settings,
        "resolve_search",
        lambda: app_settings.SearchConfig(
            enabled=False,
            api_key="",
            has_api_key=False,
            rate_limit_per_second=1.0,
            uses_brave=False,
        ),
    )
    search_module.run_search("x")
    assert slept == []
