"""Tests for the Prompt Research agent.

The feature has three properties that a green suite would otherwise miss, and
each gets its own test class because each has been a real defect elsewhere in
this repository:

* **A refusal must not read as emptiness.** A blocked search or an unreadable
  page has to reach the model as an explicit failure, or the agent concludes a
  niche is unserved when it simply could not look.
* **The loop must terminate.** A model that calls a tool on every turn must still
  produce an answer, and a repeated call must be broken rather than repeated.
* **Numbers come from a tool.** The collective confidence is computed, never
  asked for, and the validity tool is absent unless the operator enabled it.

The agent is exercised against a **scripted** model (``stream_chat`` is replaced),
so these tests are deterministic and need no network.
"""

from __future__ import annotations

import json

import pytest

from services.research import (
    agent,
    context as context_module,
    events as event_module,
    protocol,
    prompts,
    search as search_module,
    synthesis,
    tools,
    validity,
)


# --------------------------------------------------------------------------- #
# Scripted model
# --------------------------------------------------------------------------- #

def scripted_stream(script: list[list[tuple[str, str]]]):
    """A ``stream_chat`` replacement that replays a fixed turn sequence.

    Records the messages it was given so a test can assert what the agent sent
    (for example that a tool *failure* was fed back rather than dropped).
    """
    calls: list[list[dict]] = []
    state = {"index": 0}

    def _stream(messages, temperature=0.3, **kwargs):  # noqa: ANN001, ARG001
        calls.append(list(messages))
        index = state["index"]
        state["index"] += 1
        if index >= len(script):
            yield ("content", "Nothing further to add.")
            return
        for kind, text in script[index]:
            yield kind, text

    _stream.calls = calls  # type: ignore[attr-defined]
    return _stream


def json_answer(count: int = 1, summary: str = "Produced prompts.") -> str:
    """A compliant JSON-contract answer, for tests in prompt modes.

    Prompt modes *require* this shape: a prose answer parses to zero prompts and
    the run now nudges for a resend. Tests about tool mechanics therefore have to
    finish in the required format, or they measure the nudge instead of the
    mechanism they are about.
    """
    return json.dumps(
        {
            "summary": summary,
            "prompts": [
                {
                    "title": f"Prompt {index + 1}",
                    "body": f"{HOUSE_PROMPT} Variation {index + 1}.",
                    "tags": ["test"],
                    "category": 10,
                }
                for index in range(count)
            ],
        }
    )


def _tool_call_script(count: int, tool: str = "web_search") -> list[list[tuple[str, str]]]:
    """A script that calls ``tool`` once per turn, with a distinct query each time.

    Distinct queries matter: a repeated call is broken by the loop's own guard, so
    a script that repeated one query would test the guard instead of the behaviour
    under test.
    """
    return [
        [
            (
                "content",
                f'<tool_call>{{"name": "{tool}", "arguments": {{"query": "q{index}"}}}}</tool_call>',
            )
        ]
        for index in range(count)
    ]


def _install_huge_search(monkeypatch, *, chars: int = 20_000):
    """Make every search return one enormous result.

    Goes through the real ``web_search`` tool rather than replacing the tool, so
    the test exercises the same path a live run takes. The size is the point: a
    tool result can be the whole text of a web page, which is how a run that began
    inside the window pushes itself out of it.
    """

    def _search(query, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ARG001
        return search_module.SearchResponse(
            query=query,
            results=[
                search_module.SearchResult(
                    title="Huge page",
                    url="https://stock.adobe.com/search?k=x",
                    snippet="y" * chars,
                )
            ],
            ok=True,
        )

    monkeypatch.setattr(search_module, "search", _search)


@pytest.fixture()
def stub_search(monkeypatch):
    """Replace the network search with a deterministic result set.

    The URLs point at real stock marketplaces by default, because
    ``market_overview`` classifies results by host — a stub using ``example.com``
    would report "0 marketplaces", which is a different scenario from the one
    most tests mean to exercise.
    """
    _MARKETPLACES = (
        "https://www.shutterstock.com/search/x",
        "https://stock.adobe.com/search?k=x",
        "https://www.gettyimages.com/photos/x",
        "https://www.istockphoto.com/photos/x",
    )

    def _install(results=None, ok=True, error="", urls=None):
        count = results if results is not None else 3
        chosen = urls if urls is not None else [
            _MARKETPLACES[index % len(_MARKETPLACES)] for index in range(count)
        ]
        response = search_module.SearchResponse(
            query="q",
            results=[
                search_module.SearchResult(
                    title=f"Result {index}",
                    url=chosen[index % len(chosen)],
                    snippet=f"Snippet {index}",
                )
                for index in range(count)
            ],
            ok=ok,
            error=error,
        )
        monkeypatch.setattr(search_module, "search", lambda *a, **k: response)
        return response

    return _install


# --------------------------------------------------------------------------- #
# Web search — the block must be reported, never mistaken for "no results"
# --------------------------------------------------------------------------- #

class TestWebSearch:
    """The search provider refuses scripted GETs; that refusal is a fact."""

    def test_blocked_page_is_detected(self):
        interstitial = (
            '<div class="anomaly-modal__box">Unfortunately, bots use DuckDuckGo '
            "too. Please complete the following challenge</div>"
        )
        assert search_module.looks_blocked(interstitial) is True
        assert search_module.looks_blocked("<a class='result-link'>x</a>") is False

    def test_blocked_page_yields_no_parsed_results(self):
        """A block is not parsed as results — it cannot be read as a hit list."""
        assert search_module.parse_results('<div class="anomaly-modal__box"></div>') == []

    def test_lite_markup_is_parsed_with_single_quoted_classes(self):
        """The lite front-end uses single quotes; the parser must accept them.

        Getting this wrong yields zero results on a perfectly good page, which
        looks exactly like "the web has nothing on this niche".
        """
        body = (
            "<tr><td>1.&nbsp;</td><td>"
            "<a rel=\"nofollow\" href=\"https://www.shutterstock.com/search/warehouse\" "
            "class='result-link'>21+ Thousand Warehouse Images</a></td></tr>"
            "<tr><td>&nbsp;</td><td class='result-snippet'>Find Warehouse stock images.</td></tr>"
            "<tr><td>&nbsp;</td><td><span class='link-text'>www.shutterstock.com/search/warehouse</span></td></tr>"
        )
        results = search_module.parse_results(body)
        assert len(results) == 1
        assert results[0].url == "https://www.shutterstock.com/search/warehouse"
        assert results[0].title == "21+ Thousand Warehouse Images"
        assert results[0].snippet == "Find Warehouse stock images."

    def test_double_quoted_classes_are_also_parsed(self):
        """The html front-end uses double quotes; both must work."""
        body = (
            '<a class="result-link" href="https://example.com/a">Example A</a>'
            '<td class="result-snippet">Snippet A</td>'
        )
        results = search_module.parse_results(body)
        assert [result.url for result in results] == ["https://example.com/a"]

    def test_duplicate_destinations_are_collapsed(self):
        """One page must not look like two independent confirmations."""
        body = (
            '<a class="result-link" href="https://same.com/x">First</a>'
            '<a class="result-link" href="https://same.com/x">First again</a>'
            '<a class="result-link" href="https://other.com/y">Second</a>'
        )
        results = search_module.parse_results(body)
        assert [result.url for result in results] == [
            "https://same.com/x",
            "https://other.com/y",
        ]

    def test_redirect_wrapper_is_unwrapped(self):
        body = (
            '<a class="result-link" href="/l/?uddg=https%3A%2F%2Freal.example%2Fpage">'
            "Real</a>"
        )
        assert search_module.parse_results(body)[0].url == "https://real.example/page"

    def test_a_failed_search_says_so_and_forbids_the_wrong_conclusion(self):
        """The single most important string in this module.

        If a failure were rendered as an empty result list, the model would read
        "no competition". The text has to say the opposite explicitly.
        """
        response = search_module.SearchResponse(
            query="obscure niche", ok=False, error="the provider refused the request"
        )
        text = response.to_tool_text()
        assert "SEARCH FAILED" in text
        assert "Do NOT conclude" in text
        assert "no competition" in text or "no demand" in text

    def test_an_empty_result_set_is_distinguished_from_a_failure(self):
        response = search_module.SearchResponse(query="q", results=[])
        text = response.to_tool_text()
        assert "0 results" in text
        assert "SEARCH FAILED" not in text

    def test_empty_query_is_rejected_without_a_request(self):
        response = search_module.search("   ")
        assert response.ok is False
        assert "Empty query" in response.error


# --------------------------------------------------------------------------- #
# The text tool-call protocol
# --------------------------------------------------------------------------- #

class TestToolProtocol:
    """The gateway has no tool-calling API, so the protocol carries the calls."""

    def test_canonical_envelope_is_parsed(self):
        calls = protocol.parse_tool_calls(
            '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>'
        )
        assert [(call.name, call.arguments) for call in calls] == [
            ("web_search", {"query": "x"})
        ]

    def test_fenced_json_is_parsed(self):
        calls = protocol.parse_tool_calls(
            'Looking that up.\n```json\n{"name": "web_search", "arguments": {"query": "y"}}\n```'
        )
        assert calls[0].name == "web_search"

    def test_deepseek_dsml_is_parsed(self):
        """The gateway leaks tool calls as DSML text; that shape must work.

        The separator between ``<``, ``DSML`` and the keyword is not stable in the
        real output (a space appears after the angle bracket in some tags), so a
        strict pattern parses the tool name and silently drops every argument.
        """
        bar = "\uff5c"
        dsml = (
            f"<{bar}{bar}DSML{bar}{bar} calls>\n"
            f'<{bar}{bar}DSML{bar}{bar} invoke name="web_search">\n'
            f'< {bar}{bar}DSML{bar}{bar} parameter name="query" string="true">warehouse</{bar}{bar}DSML{bar}{bar} parameter>\n'
            f"</{bar}{bar}DSML{bar}{bar} invoke>\n"
            f"</{bar}{bar}DSML{bar}{bar} calls>"
        )
        calls = protocol.parse_tool_calls(dsml)
        assert len(calls) == 1
        assert calls[0].name == "web_search"
        assert calls[0].arguments == {"query": "warehouse"}

    def test_prose_mentioning_a_tool_is_not_a_call(self):
        """Otherwise the loop never terminates.

        A reply that discusses a tool in a sentence must come through as the final
        answer, not as an invocation.
        """
        text = (
            "I could use web_search to check demand, but based on what I know this "
            "niche is already crowded."
        )
        assert protocol.parse_tool_calls(text) == []

    def test_a_plain_answer_has_no_calls(self):
        assert protocol.parse_tool_calls("Here are three prompts you can use.") == []

    def test_array_of_calls_is_parsed(self):
        calls = protocol.parse_tool_calls(
            '<tool_call>[{"name": "web_search", "arguments": {"query": "a"}},'
            ' {"name": "list_categories", "arguments": {}}]</tool_call>'
        )
        assert [call.name for call in calls] == ["web_search", "list_categories"]

    def test_json_string_arguments_are_decoded(self):
        calls = protocol.parse_tool_calls(
            '<tool_call>{"name": "web_search", "arguments": "{\\"query\\": \\"z\\"}"}</tool_call>'
        )
        assert calls[0].arguments == {"query": "z"}

    def test_openai_shaped_call_is_understood(self):
        calls = protocol.parse_tool_calls(
            '<tool_call>{"type": "function", "function": {"name": "web_search",'
            ' "arguments": {"query": "w"}}}</tool_call>'
        )
        assert calls[0].name == "web_search"
        assert calls[0].arguments == {"query": "w"}

    def test_a_call_with_no_arguments_is_still_a_call(self):
        calls = protocol.parse_tool_calls('<tool_call>{"name": "list_categories"}</tool_call>')
        assert calls[0].arguments == {}

    def test_calls_are_capped_per_reply(self):
        """A model emitting dozens of calls is looping; honouring them all would
        spend the whole run's budget in one turn."""
        payload = "[" + ",".join(
            f'{{"name": "web_search", "arguments": {{"query": "q{index}"}}}}'
            for index in range(12)
        ) + "]"
        calls = protocol.parse_tool_calls(f"<tool_call>{payload}</tool_call>")
        assert len(calls) == protocol.MAX_CALLS_PER_REPLY

    def test_stripping_preserves_line_structure(self):
        """The prompt parser keys on line-anchored headings.

        Collapsing whitespace here once flattened a whole answer onto one line, so
        six prompts were recovered as one.
        """
        text = (
            "Summary line.\n"
            "<tool_call>{\"name\": \"web_search\", \"arguments\": {}}</tool_call>\n"
            "### PROMPT 1\nBody one.\n\n### PROMPT 2\nBody two."
        )
        stripped = protocol.strip_tool_calls(text)
        assert "### PROMPT 1" in stripped
        assert "### PROMPT 2" in stripped
        assert len(stripped.splitlines()) >= 4
        assert "tool_call" not in stripped

    def test_a_fenced_json_example_is_not_stripped(self):
        """A model quoting JSON must keep its example."""
        text = 'Here is the format:\n```json\n{"title": "example", "keywords": []}\n```'
        assert "example" in protocol.strip_tool_calls(text)

    def test_a_malformed_hybrid_call_is_removed(self):
        """Measured live: the model began a JSON call, then switched mid-stream to
        DeepSeek's native DSML markup, producing a hybrid with no parseable call.

        The loop therefore treated the reply as the final answer, and the UI
        offered `<tool_call>{"name": …` as a *prompt*. Any markup that could not be
        parsed must still be removed from the prose.
        """
        bar = "\uff5c"
        malformed = (
            '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</'
            f"{bar}{bar}DSML{bar}{bar} parameter>\n"
            f"</{bar}{bar}DSML{bar}{bar} invoke>\n</{bar}{bar}DSML{bar}{bar} calls>"
        )
        stripped = protocol.strip_tool_calls(malformed)
        assert "tool_call" not in stripped
        assert "web_search" not in stripped
        assert stripped == ""

    def test_an_unterminated_call_is_removed(self):
        """A truncated reply leaves an open tag with no close."""
        stripped = protocol.strip_tool_calls(
            'Some prose.\n<tool_call>{"name": "web_search", "arguments": {"query": "y"'
        )
        assert stripped == "Some prose."

    def test_stripping_a_malformed_call_cannot_yield_a_prompt(self):
        """The synthesis parser must not be able to see leftover markup."""
        malformed = (
            '<tool_call>{"name": "web_search", "arguments": '
            '{"query": "warehouse robots fulfillment center photography"}}'
        )
        drafts, _note = synthesis.parse_prompts(
            protocol.strip_tool_calls(malformed)
        )
        assert drafts == []

    def test_tool_result_envelope_names_the_tool(self):
        rendered = protocol.format_tool_result("web_search", "some text")
        assert 'name="web_search"' in rendered
        assert "some text" in rendered

    def test_a_call_error_lists_the_available_tools(self):
        rendered = protocol.format_call_error("nope", "no such tool", ["web_search"])
        assert "web_search" in rendered
        assert "could not be run" in rendered


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #

class TestSearchProviders:
    """The primary search provider rate-limits, so a second one is required.

    Measured on this machine: eight queries in three seconds got the anti-bot
    challenge on all eight, and the block persisted. A research run issues several
    queries, so a single-provider design fails exactly when it is used hardest.
    """

    def test_the_news_provider_parses_the_feed_shape(self):
        from services.research import news_search

        feed = (
            "<rss><channel><item>"
            "<title>When Will Dark Warehouses Become Common? - Forbes</title>"
            "<link>https://news.google.com/rss/articles/CBMiABC?oc=5</link>"
            "<pubDate>Thu, 03 Sep 2026 07:00:00 GMT</pubDate>"
            '<source url="https://www.forbes.com">Forbes</source>'
            "</item></channel></rss>"
        )
        results = news_search.parse_items(feed, limit=5)
        assert len(results) == 1
        assert results[0].title.startswith("When Will Dark Warehouses")
        # The publisher is the useful part for judging a source, so it becomes the
        # display URL rather than a long opaque redirect.
        assert results[0].display_url == "https://www.forbes.com"
        assert "Forbes" in results[0].snippet
        assert "2026" in results[0].snippet

    def test_the_news_provider_is_labelled_on_its_response(self, monkeypatch):
        from services.research import news_search

        feed = (
            "<rss><channel><item><title>Article</title>"
            "<link>https://news.google.com/rss/articles/x</link>"
            '<source url="https://example.com">Example</source></item></channel></rss>'
        )

        class _Response:
            headers = {"content-type": "application/rss+xml"}

            def read(self, _n=None):  # noqa: ANN001
                return feed.encode()

            def __enter__(self):
                return self

            def __exit__(self, *args):  # noqa: ANN002
                return False

        monkeypatch.setattr(
            news_search.urllib.request, "urlopen", lambda *a, **k: _Response()
        )
        response = news_search.google_news("x", limit=5, timeout=5)
        assert response.ok is True
        assert response.provider == news_search.PROVIDER_NAME

    def test_a_fallback_result_says_it_is_news_not_catalogue_data(self):
        """The limitation must be stated, or the agent over-reads the evidence.

        Keyed on ``degraded_source`` (a *lower evidence tier*), not on
        ``used_fallback``. The distinction is the point: a Brave-to-DuckDuckGo
        fallback is same-tier and returns the same kind of evidence, so flagging it
        with this caveat would be a false statement about good results.
        """
        from services.research import search as search_mod

        response = search_mod.SearchResponse(
            query="q",
            results=[
                search_mod.SearchResult(title="Article", url="https://news.example/a")
            ],
            provider="google_news",
            provider_label="Google News",
            used_fallback=True,
            degraded_source=True,
        )
        text = response.to_tool_text()
        assert "news and" in text
        assert "not how many competing stock images exist" in text

    def test_a_same_tier_fallback_carries_no_caveat(self):
        """The mirror: a general-index fallback must NOT be described as news.

        This is the defect a single ``used_fallback`` flag would have produced —
        Brave failing over to DuckDuckGo is a change of vendor, not of evidence
        quality.
        """
        from services.research import search as search_mod

        response = search_mod.SearchResponse(
            query="q",
            results=[
                search_mod.SearchResult(title="Result", url="https://stock.adobe.com/x")
            ],
            provider="duckduckgo",
            provider_label="DuckDuckGo",
            used_fallback=True,
            degraded_source=False,
        )
        text = response.to_tool_text()
        assert "news and" not in text
        assert "editorial" not in text

    def test_a_total_provider_failure_lists_every_provider(self, monkeypatch):
        """The operator must be able to tell 'rate-limited' from 'no network'."""
        from services.research import news_search
        from services.research import search as search_mod

        monkeypatch.setattr(
            search_mod,
            "_duckduckgo",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query, ok=False, error="anti-bot challenge"
            ),
        )
        monkeypatch.setattr(
            news_search,
            "google_news",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query, ok=False, error="HTTP 503"
            ),
        )

        response = search_mod.search("x")
        assert response.ok is False
        assert "every search provider failed" in response.error
        assert len(response.provider_errors) == 2
        assert any("anti-bot" in entry for entry in response.provider_errors)
        # And the model is told not to read it as "no competition".
        assert "Do NOT conclude" in response.to_tool_text()

    def test_the_primary_provider_is_preferred_when_it_works(self, monkeypatch):
        from services.research import news_search
        from services.research import search as search_mod

        monkeypatch.setattr(
            search_mod,
            "_duckduckgo",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query,
                results=[search_mod.SearchResult(title="Primary", url="https://p.example")],
                provider="duckduckgo",
                provider_label="DuckDuckGo",
            ),
        )
        monkeypatch.setattr(
            news_search,
            "google_news",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query,
                results=[search_mod.SearchResult(title="Fallback", url="https://f.example")],
            ),
        )

        response = search_mod.search("x")
        assert response.results[0].title == "Primary"
        assert response.used_fallback is False

    def test_a_fallback_result_is_marked_as_a_fallback(self, monkeypatch):
        from services.research import news_search
        from services.research import search as search_mod

        monkeypatch.setattr(
            search_mod,
            "_duckduckgo",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query, ok=False, error="blocked"
            ),
        )
        monkeypatch.setattr(
            news_search,
            "google_news",
            lambda query, **kwargs: search_mod.SearchResponse(
                query=query,
                results=[search_mod.SearchResult(title="Fallback", url="https://f.example")],
                provider="google_news",
                provider_label="Google News",
            ),
        )

        response = search_mod.search("x")
        assert response.ok is True
        assert response.used_fallback is True
        assert response.provider_label == "Google News"


class TestTools:
    def test_the_collective_score_is_computed_not_asked_for(self):
        """A model asked for three numbers will occasionally return three that
        disagree, so the average is arithmetic and lives here."""
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "subject": "warehouse robotics",
                "customer_download_confidence": 80,
                "adobe_acceptance_confidence": 60,
                "reasoning": "because",
            },
        )
        assert outcome.validity is not None
        assert outcome.validity["collective_average"] == 70.0

    def test_the_subject_is_recorded_so_the_card_can_name_what_it_judged(self):
        """Measured live: a "research a better idea" turn scored a replacement and
        the card named nothing at all, so the operator could not tell which idea
        the numbers described."""
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "subject": "cold-storage warehouse robotics",
                "customer_download_confidence": 80,
                "adobe_acceptance_confidence": 80,
                "reasoning": "because",
            },
        )
        assert outcome.validity["subject"] == "cold-storage warehouse robotics"

    def test_a_missing_subject_is_refused(self):
        """Without it the scorecard has no subject, which is the defect this
        argument exists to prevent — so it is required, not optional."""
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "customer_download_confidence": 80,
                "adobe_acceptance_confidence": 80,
                "reasoning": "because",
            },
        )
        assert outcome.validity is None
        assert outcome.degraded is True
        assert "subject" in outcome.text

    def test_a_score_below_the_target_says_so_and_asks_for_another_candidate(self):
        """The tool's reply is what steers the loop, so a below-target result must
        not read as a finished job."""
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "subject": "generic leaf background",
                "customer_download_confidence": 40,
                "adobe_acceptance_confidence": 60,
                "reasoning": "thin evidence",
            },
        )
        assert outcome.validity["collective_average"] == 50.0
        assert "BELOW" in outcome.text
        assert "different" in outcome.text
        assert "below the" in outcome.summary

    def test_a_score_at_or_above_the_target_does_not_ask_for_more(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "subject": "a strong niche",
                "customer_download_confidence": 85,
                "adobe_acceptance_confidence": 85,
                "reasoning": "strong evidence",
            },
        )
        assert outcome.validity["collective_average"] == 85.0
        assert "BELOW" not in outcome.text
        assert "clears the target" in outcome.text

    def test_the_target_is_recorded_with_the_scores(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=True),
            "assess_validity",
            {
                "subject": "x",
                "customer_download_confidence": 50,
                "adobe_acceptance_confidence": 50,
                "reasoning": "r",
            },
        )
        assert outcome.validity["target_average"] == validity.TARGET_AVERAGE

    def test_scores_outside_the_range_are_clamped(self):
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        outcome = tools.call_tool(
            registry,
            "assess_validity",
            {
                "subject": "x",
                "customer_download_confidence": 140,
                "adobe_acceptance_confidence": -20,
            },
        )
        assert outcome.validity["customer_download_confidence"] == 100.0
        assert outcome.validity["adobe_acceptance_confidence"] == 0.0

    def test_a_zero_to_one_score_is_rescaled_not_clamped_to_one_percent(self):
        """A model answering 0.8 means 80%, not 1%."""
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        outcome = tools.call_tool(
            registry,
            "assess_validity",
            {
                "subject": "x",
                "customer_download_confidence": 0.8,
                "adobe_acceptance_confidence": 0.6,
            },
        )
        assert outcome.validity["customer_download_confidence"] == 80.0
        assert outcome.validity["collective_average"] == 70.0

    def test_a_missing_score_is_refused_rather_than_defaulted(self):
        """A missing score must not silently become 0, which reads as a verdict."""
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        outcome = tools.call_tool(
            registry,
            "assess_validity",
            {"subject": "x", "customer_download_confidence": 80},
        )
        assert outcome.validity is None
        assert outcome.degraded is True
        assert "adobe_acceptance_confidence" in outcome.text

    def test_the_validity_tool_is_absent_unless_the_check_is_enabled(self):
        without = tools.registry_for(wants_prompts=True, validity_check=False)
        with_check = tools.registry_for(wants_prompts=True, validity_check=True)
        assert "assess_validity" not in without
        assert "assess_validity" in with_check

    def test_similarity_ignores_protocol_markup(self):
        """Measured live: a malformed tool-call turn was offered as a "prompt", so
        the similarity tool was asked to compare 0 real prompts and reported "not
        enough prompts to compare" — which reads as a tool fault rather than a
        malformed answer."""
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "check_prompt_similarity",
            {
                "prompts": [
                    '<tool_call>{"name": "web_search", "arguments": {"query": "a"}}</tool_call>',
                    "a real prompt about solar panels in a green field at dawn",
                    "another real prompt about frost on a rusted steel bolt",
                ]
            },
        )
        assert "not enough prompts" not in outcome.text
        assert "sufficiently distinct" in outcome.text

    def test_a_partial_market_overview_failure_is_degraded(self, monkeypatch):
        """A share computed over fewer results than the overview claims is exactly
        what the operator needs to see."""
        import services.research.tools as tools_module

        calls = {"n": 0}
        original = tools_module.search_module.search

        def _sometimes(query, **kwargs):  # noqa: ANN001, ARG001
            calls["n"] += 1
            if calls["n"] == 1:
                return search_module.SearchResponse(query=query, ok=False, error="blocked")
            return original(query, **kwargs)

        monkeypatch.setattr(tools_module.search_module, "search", _sometimes)
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "market_overview",
            {"niche": "warehouse robots"},
        )
        assert outcome.degraded is True
        assert "do not read these as" in outcome.text

    def test_a_news_fallback_market_overview_says_the_share_is_incomplete(self):
        import services.research.tools as tools_module

        original = tools_module.search_module.search
        try:
            tools_module.search_module.search = lambda *a, **k: search_module.SearchResponse(
                query="q",
                results=[
                    search_module.SearchResult(title="Article", url="https://news.example/a")
                ],
                provider="google_news",
                provider_label="Google News",
                used_fallback=True,
                # A lower evidence tier is what makes the share incomplete.
                degraded_source=True,
            )
            outcome = tools.call_tool(
                tools.registry_for(wants_prompts=True, validity_check=False),
                "market_overview",
                {"niche": "x"},
            )
        finally:
            tools_module.search_module.search = original

        assert outcome.degraded is True
        assert "news fallback" in outcome.summary
        assert "does NOT show how many competing stock images" in outcome.text

    def test_the_similarity_tool_is_absent_when_no_prompts_are_wanted(self):
        assert "check_prompt_similarity" not in tools.registry_for(
            wants_prompts=False, validity_check=False
        )
        assert "check_prompt_similarity" in tools.registry_for(
            wants_prompts=True, validity_check=False
        )

    def test_market_overview_never_presents_supply_as_demand(self, stub_search):
        """The tool most likely to be over-read.

        The stub is required: without a working search the tool reports a total
        failure, and the guidance text never renders — which would make this test
        pass for the wrong reason.
        """
        stub_search(results=4)
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "market_overview",
            {"niche": "warehouse robots"},
        )
        assert "NOT how many customers" in outcome.text
        assert "No tool here can measure customer demand" in outcome.text
        assert "demand picture is unverified" in outcome.text

    def test_market_overview_reports_a_total_search_failure(self, monkeypatch):
        """A failed overview must not read as an empty niche."""
        import services.research.tools as tools_module

        monkeypatch.setattr(
            tools_module.search_module,
            "search",
            lambda *a, **k: search_module.SearchResponse(
                query="q", ok=False, error="blocked"
            ),
        )
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "market_overview",
            {"niche": "x"},
        )

        assert outcome.degraded is True
        assert "NOT evidence" in outcome.text

    def test_catalogue_count_is_quoted_from_the_result(self):
        results = [
            search_module.SearchResult(
                title="21+ Thousand Automated Robotics Warehouse Royalty-Free Images",
                url="https://www.shutterstock.com/search/x",
                snippet="",
            )
        ]
        assert tools._largest_catalogue_count(results) == "21+ Thousand"

    def test_marketplace_results_are_recognised_by_host(self):
        """The saturation signal depends on this classification being right."""
        assert tools._is_marketplace("https://www.shutterstock.com/search/x") is True
        assert tools._is_marketplace("https://stock.adobe.com/search?k=x") is True
        assert tools._is_marketplace("https://blog.example.com/post") is False
        # A look-alike host must not count as a marketplace.
        assert tools._is_marketplace("https://notshutterstock.com/x") is False

    def test_prompt_similarity_flags_near_identical_prompts(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "check_prompt_similarity",
            {
                "prompts": [
                    "aerial drone photograph of solar panels in a green field at dawn",
                    "aerial drone photograph of solar panels in a green field at dusk",
                    "close macro of frost crystals on a rusted steel bolt",
                ]
            },
        )
        assert outcome.degraded is True
        assert "#1 and #2" in outcome.text

    def test_prompt_similarity_passes_distinct_prompts(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "check_prompt_similarity",
            {
                "prompts": [
                    "aerial drone photograph of solar panels in a green field",
                    "close macro of frost crystals on a rusted steel bolt",
                    "wide shot of an empty subway platform at midnight",
                ]
            },
        )
        assert outcome.degraded is False
        assert "sufficiently distinct" in outcome.text

    def test_restrictions_tool_catches_a_known_restricted_term(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "check_restrictions",
            {"terms": ["a photograph of the Eiffel Tower at night"]},
        )
        assert outcome.degraded is True
        assert "RESTRICTED TERMS FOUND" in outcome.text

    def test_restrictions_tool_passes_clear_wording(self):
        outcome = tools.call_tool(
            tools.registry_for(wants_prompts=True, validity_check=False),
            "check_restrictions",
            {"terms": ["an unmanned warehouse floor with epoxy markings"]},
        )
        assert outcome.degraded is False

    def test_a_crashing_tool_is_reported_not_raised(self):
        """A tool bug must not abort a run that could still answer."""
        registry = tools.registry_for(wants_prompts=True, validity_check=False)
        exploding = tools.Tool(
            name="explode",
            description="boom",
            parameters={},
            run=lambda arguments: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        registry["explode"] = exploding
        outcome = tools.call_tool(registry, "explode", {})
        assert outcome.degraded is True
        assert "internal error" in outcome.text

    def test_an_unknown_tool_is_reported(self):
        outcome = tools.call_tool({}, "nope", {})
        assert outcome.degraded is True

    def test_a_query_list_is_coerced_into_a_string(self):
        """Models routinely send a list where a string was asked for."""
        assert tools._text({"query": ["alpha", "beta"]}, "query") == "alpha beta"


# --------------------------------------------------------------------------- #
# Prompt synthesis
# --------------------------------------------------------------------------- #

HOUSE_PROMPT = (
    "Epic commercial stock photograph of a vast automated greenhouse with "
    "robotic arms tending leafy crops under diffuse volumetric daylight, "
    "wide-angle 20mm lens, f/6.3, deep cinematic focus across the 16:9 frame, "
    "clean editorial copy space in the upper third, unmanned, pristine surfaces, "
    "zero text, zero brand logos, ready for high-resolution upscaling. --ar 16:9"
)


class TestSynthesis:
    def test_delimited_blocks_are_parsed(self):
        """Kept so a conversation stored before the JSON contract still parses."""
        answer = (
            "Here is what I produced.\n\n"
            f"### PROMPT 1\n{HOUSE_PROMPT}\n\n"
            f"### PROMPT 2\n{HOUSE_PROMPT.replace('greenhouse', 'factory')}\n"
        )
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 2
        assert note == ""
        assert drafts[0].body.startswith("Epic commercial")

    def test_a_numbered_list_is_recovered_and_the_fallback_is_announced(self):
        """A silent fallback would present a guess as structured output."""
        answer = (
            f"1. {HOUSE_PROMPT}\n\n"
            f"2. {HOUSE_PROMPT.replace('greenhouse', 'datacentre')}\n"
        )
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 2
        assert note != ""
        assert "numbered list" in note

    def test_paragraph_fallback_is_announced(self):
        answer = f"{HOUSE_PROMPT}\n\n{HOUSE_PROMPT.replace('greenhouse', 'shipyard')}"
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 2
        assert "paragraphs" in note

    def test_an_unusable_answer_yields_no_prompts_and_says_why(self):
        drafts, note = synthesis.parse_prompts("I cannot help with that.")
        assert drafts == []
        assert note != ""

    def test_a_missing_aspect_token_is_warned_about(self):
        warnings = synthesis.validate_prompt(
            "A commercial stock photograph of a factory floor with machines and "
            "clean surfaces and volumetric daylight and deep focus throughout."
        )
        assert any("--ar 16:9" in warning for warning in warnings)

    def test_a_restricted_term_is_warned_about(self):
        warnings = synthesis.validate_prompt(
            HOUSE_PROMPT + " Featuring the Eiffel Tower in the distance."
        )
        assert any("known-restrictions" in warning for warning in warnings)

    def test_a_short_prompt_is_warned_about(self):
        assert synthesis.validate_prompt("a warehouse. --ar 16:9")

    def test_a_compliant_prompt_has_no_warnings(self):
        assert synthesis.validate_prompt(HOUSE_PROMPT) == []

    def test_overlapping_prompts_are_flagged_and_only_the_first_is_kept(self):
        """The batch guarantee: near-identical prompts become near-identical
        images, and Adobe refuses similar content."""
        answer = (
            f"### PROMPT 1\n{HOUSE_PROMPT}\n\n"
            f"### PROMPT 2\n{HOUSE_PROMPT}\n\n"
            f"### PROMPT 3\n{HOUSE_PROMPT}\n"
        )
        drafts, pairs, _note, _summary = synthesis.build_drafts(answer)
        assert len(drafts) == 3
        assert pairs
        assert drafts[1].duplicate_of == 1
        assert drafts[2].duplicate_of is None or drafts[2].duplicate_of == 1
        assert len(synthesis.saveable_prompts(drafts)) < 3

    def test_distinct_prompts_are_all_saveable(self):
        """Swapping one noun is NOT enough to make two prompts distinct.

        This is the batch mode's real constraint: Adobe refuses *similar content*,
        and two prompts that differ only in the subject noun will produce frames a
        reviewer considers the same submission. Every axis has to move — subject,
        setting, activity, time of day, camera position.
        """
        answer = (
            "### PROMPT 1\n"
            "Epic commercial stock photograph of a vast automated greenhouse with "
            "robotic arms tending leafy crops under diffuse daylight, wide-angle "
            "20mm lens, f/6.3, deep focus, clean copy space, unmanned, pristine, "
            "zero text, ready for high-resolution upscaling. --ar 16:9\n\n"
            "### PROMPT 2\n"
            "Overhead drone photograph of an autonomous container terminal at "
            "midnight, gantry cranes and stacked steel boxes lit by sodium floodlights, "
            "telephoto 135mm lens, f/8, clean copy space, no people, ready for "
            "high-resolution upscaling. --ar 16:9\n\n"
            "### PROMPT 3\n"
            "Low-angle macro photograph of frost crystals forming on a rusted steel "
            "bolt in a frozen shipyard at dawn, 100mm lens, f/4, shallow depth, "
            "muted cold palette, no text, ready for high-resolution upscaling. --ar 16:9\n"
        )
        drafts, pairs, _note, _summary = synthesis.build_drafts(answer)
        assert pairs == []
        assert len(synthesis.saveable_prompts(drafts)) == 3

    # --- the JSON contract ------------------------------------------------ #

    def test_the_json_contract_is_parsed_with_every_field(self):
        """The point of the contract: the fields arrive labelled."""
        answer = json.dumps(
            {
                "summary": "Two logistics prompts.",
                "prompts": [
                    {
                        "title": "Sorting hall at dusk",
                        "body": HOUSE_PROMPT,
                        "tags": ["logistics", "automation"],
                        "category": 10,
                        "notes": "Best of the set.",
                    },
                    {
                        "title": "Cold-chain loading bay",
                        "body": HOUSE_PROMPT.replace("greenhouse", "shipyard"),
                        "tags": ["cold chain"],
                        "category": 20,
                    },
                ],
            }
        )
        drafts, note, summary = synthesis.parse_prompts_with_summary(answer)
        assert len(drafts) == 2
        assert note == ""
        assert summary == "Two logistics prompts."
        assert drafts[0].title == "Sorting hall at dusk"
        assert drafts[0].tags == ["logistics", "automation"]
        assert drafts[0].category == 10
        assert drafts[0].notes == "Best of the set."
        assert drafts[0].to_dict()["category_name"] == "Industry"
        assert drafts[1].category == 20

    def test_a_fenced_json_payload_is_parsed(self):
        """Models add a ```json fence even when told not to."""
        answer = "```json\n" + json.dumps(
            {"summary": "one", "prompts": [{"body": HOUSE_PROMPT}]}
        ) + "\n```"
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 1
        assert note == ""
        assert drafts[0].body == HOUSE_PROMPT

    def test_json_surrounded_by_prose_is_still_parsed(self):
        answer = (
            "Sure, here you go:\n\n"
            + json.dumps({"summary": "one", "prompts": [{"body": HOUSE_PROMPT}]})
            + "\n\nLet me know if you want more."
        )
        drafts, _note = synthesis.parse_prompts(answer)
        assert len(drafts) == 1

    def test_a_brace_inside_a_body_does_not_truncate_the_payload(self):
        """A brace-matching scan, not a regex: `{` is legitimate prompt text.

        A regex ending at the last `}` would still work here; one ending at the
        first would silently cut the payload in half. The two-prompt form is what
        distinguishes them.
        """
        body = HOUSE_PROMPT + " Bracket set {A, B} on the wall."
        answer = json.dumps(
            {"summary": "one", "prompts": [{"body": body}, {"body": HOUSE_PROMPT}]}
        )
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 2
        assert note == ""
        assert "{A, B}" in drafts[0].body
        assert drafts[1].body == HOUSE_PROMPT

    def test_an_invented_category_is_dropped_and_reported(self):
        """Adobe's importer rejects a code it does not know.

        The complaint is attached to the *prompt*, not the run: it is about one
        specific entry, and a run-level banner would not say which one.
        """
        answer = json.dumps(
            {
                "summary": "one",
                "prompts": [{"body": HOUSE_PROMPT, "category": 99}],
            }
        )
        drafts, note = synthesis.parse_prompts(answer)
        assert drafts[0].category is None
        assert note == ""
        assert any(
            "99" in warning and "not one of Adobe's codes" in warning
            for warning in drafts[0].warnings
        )

    def test_a_named_category_is_resolved_to_its_code(self):
        answer = json.dumps(
            {
                "summary": "one",
                "prompts": [{"body": HOUSE_PROMPT, "category": "Technology"}],
            }
        )
        drafts, _note = synthesis.parse_prompts(answer)
        assert drafts[0].category == 19

    def test_a_json_entry_without_a_body_is_skipped_and_reported(self):
        answer = json.dumps(
            {
                "summary": "one",
                "prompts": [{"title": "no body"}, {"body": HOUSE_PROMPT}],
            }
        )
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 1
        assert "no `body`" in note

    def test_a_bare_string_entry_is_still_a_prompt(self):
        """Discarding the one field the feature depends on over a missing
        wrapper would be perverse."""
        answer = json.dumps({"summary": "one", "prompts": [HOUSE_PROMPT]})
        drafts, _note = synthesis.parse_prompts(answer)
        assert len(drafts) == 1
        assert drafts[0].body == HOUSE_PROMPT

    def test_json_with_no_prompts_falls_back_to_prose_and_says_so(self):
        answer = json.dumps({"summary": "sorry"}) + "\n\n" + HOUSE_PROMPT
        drafts, note = synthesis.parse_prompts(answer)
        assert len(drafts) == 1
        assert note != ""

    def test_tags_are_normalised_from_a_csv_string(self):
        answer = json.dumps(
            {
                "summary": "one",
                "prompts": [{"body": HOUSE_PROMPT, "tags": "#warehouse, robots"}],
            }
        )
        drafts, _note = synthesis.parse_prompts(answer)
        assert drafts[0].tags == ["warehouse", "robots"]

    def test_answer_text_renders_the_payload_as_readable_prose(self):
        """The transcript must not show raw JSON."""
        answer = json.dumps(
            {
                "summary": "Two prompts for logistics.",
                "prompts": [{"body": HOUSE_PROMPT}, {"body": HOUSE_PROMPT + " Two."}],
            }
        )
        rendered = synthesis.answer_text(answer)
        assert rendered.startswith("Two prompts for logistics.")
        assert "2 prompts written" in rendered
        assert "{\"summary\"" not in rendered

    def test_answer_text_leaves_a_non_json_answer_alone(self):
        prose = "The evidence is thin, so I would not pursue this niche."
        assert synthesis.answer_text(prose) == prose

    def test_answer_text_leaves_json_that_is_not_a_prompt_payload_alone(self):
        """A validity run answers in prose that may mention a JSON block."""
        answer = 'The tool returned {"score": 40} which is weak.'
        assert synthesis.answer_text(answer) == answer

    def test_the_format_instruction_shows_the_schema_not_a_delimiter(self):
        instruction = synthesis.prompt_format_instruction(4)
        assert "4 entries" in instruction
        assert synthesis.ASPECT_TOKEN in instruction
        assert "\"summary\"" in instruction
        assert "\"prompts\"" in instruction
        assert "\"body\"" in instruction
        assert "ONE JSON object" in instruction

    def test_the_format_instruction_discourages_padding(self):
        """Asking for exactly N yields N copies of one idea."""
        assert "do NOT pad" in synthesis.prompt_format_instruction(6)


# --------------------------------------------------------------------------- #
# Validity
# --------------------------------------------------------------------------- #

class TestValidity:
    def test_bands_are_derived_from_the_score(self):
        assert validity.band_for(85) == validity.BAND_STRONG
        assert validity.band_for(60) == validity.BAND_MODERATE
        assert validity.band_for(10) == validity.BAND_WEAK

    def test_no_assessment_yields_no_view(self):
        """A zeroed scorecard would read as a verdict on the idea."""
        assert validity.describe(None) is None
        assert validity.describe({}) is None

    def test_the_average_is_recomputed_from_the_components(self):
        """A stored average that disagrees cannot be displayed."""
        view = validity.describe(
            {
                "customer_download_confidence": 80,
                "adobe_acceptance_confidence": 60,
                "collective_average": 5,
            }
        )
        assert view.collective_average == 70.0

    def test_the_disclaimer_states_the_scores_are_not_a_measurement(self):
        view = validity.describe(
            {"customer_download_confidence": 80, "adobe_acceptance_confidence": 60}
        )
        payload = view.to_dict()
        assert "not a measurement" in payload["disclaimer"]
        assert "keyword volume" in payload["disclaimer"]

    def test_a_weak_score_recommends_researching_a_better_idea(self):
        view = validity.describe(
            {"customer_download_confidence": 20, "adobe_acceptance_confidence": 20}
        )
        assert view.collective_band == validity.BAND_WEAK
        assert "better idea" in view.recommendation

    def test_the_two_follow_up_actions_are_offered(self):
        actions = {action["id"] for action in validity.FOLLOW_UP_ACTIONS}
        assert actions == {validity.CONTINUE_ACTION, validity.RESEARCH_AGAIN_ACTION}

    def test_a_mode_that_writes_no_prompts_is_not_offered_prompts(self):
        """Measured live in "Find ideas": the card offered "Continue with these
        confidence rates", whose canned message says *generate the prompts*.

        `ideas` never writes prompts, so the button promised an outcome the run
        could not produce — the operator pressed it and got a second opinion
        instead of the prompts they had been told to expect.
        """
        actions = validity.follow_up_actions(can_produce_prompts=False)
        continue_action = next(
            action for action in actions if action["id"] == validity.CONTINUE_ACTION
        )
        assert "prompt" not in continue_action["message"].casefold()
        assert continue_action["message"] != validity.CONTINUE_MESSAGE
        # The other option is unchanged: the decision is the same either way.
        assert any(
            action["id"] == validity.RESEARCH_AGAIN_ACTION for action in actions
        )

    def test_a_mode_that_writes_prompts_keeps_the_release_wording(self):
        """The mirror, so the branch cannot pass by never using the release text.

        The release wording is load-bearing: :func:`prompts.is_release_message`
        matches it to turn the gate off, so replacing it here would silently
        reintroduce the "no prompts after Continue" defect.
        """
        actions = validity.follow_up_actions(can_produce_prompts=True)
        continue_action = next(
            action for action in actions if action["id"] == validity.CONTINUE_ACTION
        )
        assert continue_action["message"] == validity.CONTINUE_MESSAGE

    def test_the_ideas_continue_message_does_not_release_the_prompt_gate(self):
        """A no-prompts mode must not be able to talk itself into prompts."""
        assert not prompts.is_release_message(validity.CONTINUE_IDEA_MESSAGE)


# --------------------------------------------------------------------------- #
# The agent loop
# --------------------------------------------------------------------------- #

class TestAgentLoop:
    def test_a_tool_call_is_run_and_its_result_fed_back(self, monkeypatch, stub_search):
        stub_search()
        stream = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>',
                    )
                ],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="warehouse robots")
        )

        kinds = [payload["type"] for payload in emitted]
        assert event_module.TOOL_CALL in kinds
        assert event_module.TOOL_RESULT in kinds
        # The result must reach the model as a tool_result message.
        second_turn = stream.calls[1]
        assert any(
            "tool_result" in str(message.get("content", "")) for message in second_turn
        )
        # A prompt-mode run answers with the JSON contract, so that is what the
        # stored answer is rendered from — not the raw payload.
        assert "1 prompt written" in result["message"]
        assert any(payload["type"] == event_module.PROMPTS for payload in emitted)

    def test_a_failed_search_reaches_the_model_as_a_failure(self, monkeypatch):
        """The whole point: a block must never look like an empty result set."""
        monkeypatch.setattr(
            search_module,
            "search",
            lambda *a, **k: search_module.SearchResponse(
                query="q", ok=False, error="anti-bot challenge"
            ),
        )
        stream = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>',
                    )
                ],
                [("content", "I could not verify demand.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="obscure niche")
        )

        second_turn = " ".join(
            str(message.get("content", "")) for message in stream.calls[1]
        )
        assert "SEARCH FAILED" in second_turn
        assert "Do NOT conclude" in second_turn
        assert "no competition" in second_turn
        # And the operator is told the step degraded.
        results = [p for p in emitted if p["type"] == event_module.TOOL_RESULT]
        assert results[0]["ok"] is False

    def test_an_unknown_tool_name_is_corrected_rather_than_fatal(self, monkeypatch):
        stream = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "not_a_tool", "arguments": {}}</tool_call>',
                    )
                ],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(agent.RunRequest(mode="static", message="x"))
        # The available tools are listed back, which is the correction.
        second_turn = " ".join(
            str(message.get("content", "")) for message in stream.calls[1]
        )
        assert "web_search" in second_turn
        assert "no tool called" in second_turn
        # The run still finished with a usable answer.
        assert result["message"]
        assert any(payload["type"] == event_module.RUN_FINISHED for payload in emitted)

    def test_a_repeated_identical_call_is_broken(self, monkeypatch, stub_search):
        """Repeating a call cannot produce new information, and waiting for the
        budget to expire would just waste time before the same answer."""
        stub_search()
        call = (
            "content",
            '<tool_call>{"name": "web_search", "arguments": {"query": "same"}}</tool_call>',
        )
        stream = scripted_stream([[call], [call], [call], [call], [("content", "Done.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=10)
        )
        summaries = [
            payload.get("summary", "")
            for payload in emitted
            if payload["type"] == event_module.TOOL_RESULT
        ]
        assert any("skipped" in summary.lower() for summary in summaries)

    def test_the_tool_budget_is_enforced_and_an_answer_is_still_produced(
        self, monkeypatch, stub_search
    ):
        """A model that calls a tool on every turn must still terminate."""
        stub_search()
        counter = {"n": 0}

        def endless(messages, temperature=0.3, **kwargs):  # noqa: ANN001, ARG001
            counter["n"] += 1
            yield (
                "content",
                '<tool_call>{"name": "web_search", "arguments": {"query": "q'
                f'{counter["n"]}"}}}}</tool_call>',
            )

        monkeypatch.setattr(agent, "stream_chat", endless)

        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=3)
        )
        calls = [p for p in emitted if p["type"] == event_module.TOOL_CALL]
        assert len(calls) <= 3 + protocol.MAX_CALLS_PER_REPLY
        assert any(
            payload["type"] == event_module.NOTICE and "limit" in payload["text"]
            for payload in emitted
        )
        # The run still ends.
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_a_research_run_that_answers_without_researching_is_nudged(
        self, monkeypatch, stub_search
    ):
        """Measured live: asked to research a niche with the gate on, the model
        replied "I'll research this niche before recording any confidence scores."
        and stopped — announcing research it never performed.

        The reply was valid prose, so the protocol accepted it as the final answer
        and the operator got an unresearched opinion presented as a researched one.
        """
        stub_search()
        stream = scripted_stream(
            [
                [("content", "I'll research this niche before recording any scores.")],
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>',
                    )
                ],
                [("content", "Now here is what I found.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="warehouse robots", validity_check=True)
        )

        assert any(
            payload["type"] == event_module.NOTICE and "without researching" in payload["text"]
            for payload in emitted
        )
        # The run did perform research before answering.
        assert any(payload["type"] == event_module.TOOL_CALL for payload in emitted)
        assert result["message"] == "Now here is what I found."

    def test_a_static_run_is_not_nudged_to_search(self, monkeypatch):
        """The operator's hint is the authority on the subject in `static` mode,
        and refusing to answer without a search would add latency to the one mode
        that does not need it."""
        stream = scripted_stream([[("content", "Here is your prompt. --ar 16:9")]])
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))
        assert not any(
            payload["type"] == event_module.NOTICE and "without researching" in payload.get("text", "")
            for payload in emitted
        )
        assert len(stream.calls) == 1

    def test_the_research_nudge_is_bounded(self, monkeypatch):
        """A model that never calls a tool must still finish, not loop."""
        stream = scripted_stream(
            [[("content", "Let me think about it.")] for _ in range(6)]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        nudges = [
            payload
            for payload in emitted
            if payload["type"] == event_module.NOTICE
            and "without researching" in payload.get("text", "")
        ]
        assert len(nudges) == agent.MAX_TOOL_NUDGES
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_a_follow_up_turn_is_not_told_it_has_no_evidence(self, monkeypatch):
        """Measured live: pressing "Continue with this idea and generate the
        prompts" produced the notice "The agent tried to answer without
        researching anything" — on a turn whose transcript already held every
        tool result from the earlier turns.

        `calls_made` counts *this* turn's calls, but "you have no evidence" is a
        property of the whole conversation. Firing here told a model that had
        done nothing wrong that it had "only your own recall", and spent a turn
        correcting it.
        """
        stream = scripted_stream([[("content", "Here are the prompts. --ar 16:9")]])
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(
                mode="research",
                message="Continue with this idea and generate the prompts we discussed.",
                validity_check=True,
                released=True,
                history=[
                    {"role": "user", "content": "automated warehouses"},
                    {"role": "assistant", "content": "Here is my verdict."},
                ],
            )
        )
        assert not any(
            payload["type"] == event_module.NOTICE
            and "without researching" in payload.get("text", "")
            for payload in emitted
        )
        # The nudge would have cost a turn; the answer came straight back.
        assert len(stream.calls) == 1
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_an_opening_turn_with_no_history_is_still_nudged(self, monkeypatch):
        """The mirror of the test above, so the guard cannot pass by never firing."""
        stream = scripted_stream(
            [
                [("content", "I will look into that shortly.")],
                [("content", "Done.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="warehouse robots", validity_check=True)
        )
        assert any(
            payload["type"] == event_module.NOTICE
            and "without researching" in payload.get("text", "")
            for payload in emitted
        )
        # The nudge cost a turn: the model was asked again rather than accepted.
        assert len(stream.calls) >= 2
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_every_run_ends_with_a_terminal_event(self, monkeypatch):
        monkeypatch.setattr(agent, "stream_chat", scripted_stream([[("content", "Hi.")]]))
        for mode in ("static", "batch", "research", "ideas"):
            emitted, _ = agent.collect(agent.RunRequest(mode=mode, message="x"))
            assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_an_empty_reply_finalises_the_run_instead_of_discarding_it(self, monkeypatch):
        """Measured live: the model answered with a tool call the parser could not
        read, the turn was treated as empty, and a run that had already gathered
        its evidence was thrown away — which the operator experiences as a spinner
        that ends in nothing. The gathered work must survive."""
        monkeypatch.setattr(
            agent,
            "stream_chat",
            scripted_stream(
                [[("thinking", "Considering the niche.")], [("content", "")], [("content", "")], [("content", "")]]
            ),
        )
        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))
        assert any(
            payload["type"] == event_module.NOTICE and "stopped producing" in payload["text"]
            for payload in emitted
        )
        assert emitted[-1]["type"] == event_module.RUN_FINISHED
        # The reasoning gathered before the silence is still reported.
        assert emitted[-1]["thinking"] == "Considering the niche."

    def test_an_unparseable_tool_call_is_corrected_by_name(self, monkeypatch):
        """Telling the model its reply was 'empty' when it actually sent
        unparseable markup is a useless correction — it repeats the same fault.
        The retry has to name the real problem.

        Measured: a tool call cut off mid-stream parses as no call AND strips to
        no prose, so it lands in the empty-reply branch with the wrong explanation.
        """
        truncated_call = '<tool_call>{"name": "market_overview", "arguments": {"niche": "log'
        stream = scripted_stream([[("content", truncated_call)], [("content", "Done.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))
        corrections = [
            str(message.get("content") or "")
            for message in stream.calls[1]
            if isinstance(message, dict) and message.get("role") == "user"
        ]
        # The correction must name the markup as the fault and show the shape to
        # resend. Asserted on the *shape* of the correction, not one exact phrase:
        # the wording was tightened once already and a phrase-keyed assertion made
        # that a test failure instead of an improvement.
        assert any("could not be read" in text for text in corrections)
        assert any("<tool_call>" in text for text in corrections)
        assert not any("reply was empty" in text for text in corrections)
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_a_stream_failure_ends_the_run_cleanly(self, monkeypatch):
        """A dead endpoint must produce an error event and a terminal event, not
        a hung stream."""
        from services.llm_client import LLMError

        def exploding(messages, temperature=0.3, **kwargs):  # noqa: ANN001, ARG001
            raise LLMError("HTTP 401: bad key")
            yield  # pragma: no cover - makes this a generator

        monkeypatch.setattr(agent, "stream_chat", exploding)
        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))
        assert any(payload["type"] == event_module.ERROR for payload in emitted)
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_tool_markup_is_never_streamed_into_the_transcript(self, monkeypatch):
        """The invariant is mode-independent: the protocol markup is the agent's
        plumbing, not its words.

        Measured live on a research run with the validity gate on — the gate makes
        `wants_prompts` false, which re-enabled content streaming, so the raw
        `<tool_call>{…` text was stored as the run's transcript and rendered to the
        operator as the agent's answer.
        """
        call = '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>'
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", call)], [("content", "Done.")]])
        )
        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        streamed = "".join(
            payload["text"] for payload in emitted if payload["type"] == event_module.MESSAGE
        )
        assert "<tool_call" not in streamed
        assert "DSML" not in streamed
        assert "<tool_call" not in result["transcript"]
        assert "<tool_call" not in result["message"]

    def test_markup_split_across_deltas_is_still_caught(self, monkeypatch):
        """A tool-call opener arrives token by token; the check cannot look at one
        delta in isolation.

        `ideas` is a prose mode, so its content *is* streamed — which is what makes
        the hold-back meaningful here.
        """
        monkeypatch.setattr(
            agent,
            "stream_chat",
            scripted_stream(
                [[("content", "Let me look. <tool"), ("content", '_call>{"name": "web_search"}')]]
            ),
        )
        emitted, _ = agent.collect(agent.RunRequest(mode="ideas", message="x"))
        streamed = "".join(
            payload["text"] for payload in emitted if payload["type"] == event_module.MESSAGE
        )
        assert "tool_call" not in streamed
        assert "web_search" not in streamed
        # The sentence before the marker is kept: the operator was already reading it.
        assert "Let me look." in streamed

    def test_a_payload_run_does_not_stream_its_json_as_chat(self, monkeypatch):
        """A prompt run's content is the JSON contract, which the cards render."""
        payload = json.dumps({"summary": "s", "prompts": [{"body": HOUSE_PROMPT}]})
        monkeypatch.setattr(agent, "stream_chat", scripted_stream([[("content", payload)]]))
        emitted, result = agent.collect(
            agent.RunRequest(mode="static", message="x", count=1)
        )
        assert not [p for p in emitted if p["type"] == event_module.MESSAGE]
        assert any(p["type"] == event_module.PROMPTS for p in emitted)
        # The stored answer is the rendered form, not the raw JSON.
        assert '{"summary"' not in result["message"]
        assert "1 prompt written" in result["message"]

    def test_thinking_is_streamed_and_accumulated(self, monkeypatch):
        """The operator watches the reasoning, and a reload replays it."""
        monkeypatch.setattr(
            agent,
            "stream_chat",
            scripted_stream(
                [[("thinking", "Let me think. "), ("thinking", "More thought."), ("content", "Answer.")]]
            ),
        )
        emitted, result = agent.collect(agent.RunRequest(mode="static", message="x"))
        thinking_events = [p for p in emitted if p["type"] == event_module.THINKING]
        assert len(thinking_events) == 2
        assert result["thinking"] == "Let me think. More thought."

    def test_prompts_are_extracted_only_when_the_mode_wants_them(self, monkeypatch):
        answer = f"### PROMPT 1\n{HOUSE_PROMPT}\n"
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", answer)]])
        )

        _emitted, prompted = agent.collect(agent.RunRequest(mode="batch", message="x"))
        assert len(prompted["prompts"]) == 1

        # `ideas` proposes niches; generating prompts would answer a question
        # that was not asked.
        _emitted, ideas = agent.collect(agent.RunRequest(mode="ideas", message="x"))
        assert ideas["prompts"] == []

    def test_the_validity_gate_suppresses_prompts(self, monkeypatch, stub_search):
        """Measured live: with the gate on, the agent was told to score and *stop*
        while the format block simultaneously asked for prompts. The model detected
        the contradiction in its own reasoning ("Wait, there's a conflict") and then
        emitted a malformed turn because it could not satisfy both.
        """
        stub_search()
        answer = f"### PROMPT 1\n{HOUSE_PROMPT}\n"
        tool_turn = (
            "content",
            '<tool_call>{"name": "web_search", "arguments": {"query": "x"}}</tool_call>',
        )

        # Gate off: prompts are the deliverable.
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[tool_turn], [("content", answer)]])
        )
        _emitted, without_gate = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=False)
        )
        assert len(without_gate["prompts"]) == 1

        # Gate on: the run ends with a verdict, and the operator continues.
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[tool_turn], [("content", answer)]])
        )
        _emitted, with_gate = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        assert with_gate["prompts"] == []

    def test_the_format_block_is_absent_when_the_validity_gate_is_on(self, monkeypatch):
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        user_turn = stream.calls[0][-1]["content"]
        assert synthesis.BLOCK_PREFIX not in user_turn

    def test_the_similarity_tool_is_absent_while_the_validity_gate_is_on(self):
        """Nothing has been drafted yet, so comparing prompts is meaningless."""
        from services.research import tools as tools_module

        with_gate = tools_module.registry_for(wants_prompts=False, validity_check=True)
        assert "check_prompt_similarity" not in with_gate
        assert "assess_validity" in with_gate

    def test_duplicate_prompts_are_reported_and_not_pre_selected(self, monkeypatch):
        answer = f"### PROMPT 1\n{HOUSE_PROMPT}\n\n### PROMPT 2\n{HOUSE_PROMPT}\n"
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", answer)]])
        )
        emitted, result = agent.collect(agent.RunRequest(mode="batch", message="x"))
        assert len(result["prompts"]) == 2
        assert any(
            payload["type"] == event_module.NOTICE and "overlap" in payload["text"]
            for payload in emitted
        )
        prompts_event = next(p for p in emitted if p["type"] == event_module.PROMPTS)
        assert len(prompts_event["saveable"]) < len(prompts_event["prompts"])

    def test_the_validity_scores_become_their_own_event(self, monkeypatch):
        stub = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "assess_validity", "arguments": '
                        '{"subject": "warehouse robotics", '
                        '"customer_download_confidence": 75, '
                        '"adobe_acceptance_confidence": 65, "reasoning": "r"}}</tool_call>',
                    )
                ],
                [("content", "Here is my verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stub)
        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        validity_events = [p for p in emitted if p["type"] == event_module.VALIDITY]
        assert len(validity_events) == 1
        assert validity_events[0]["validity"]["collective_average"] == 70.0
        assert len(validity_events[0]["follow_up_actions"]) == 2
        assert result["validity"]["collective_average"] == 70.0
        # The subject travels with the scores, so the card can name what it judged.
        assert result["validity"]["subject"] == "warehouse robotics"

    def test_the_validity_event_carries_the_whole_presented_view(self, monkeypatch):
        """The streaming card and the reopened card must show the same thing.

        The tool returns the raw assessment, which has no `meets_target`,
        `collective_band`, `collective_label`, `recommendation` or `disclaimer` —
        all of them derived by `validity.describe`, which only the *storage* path
        called. Measured live: an idea scoring **73.5** streamed a card reading
        "Reaches the 80% target." (`undefined` is falsy but not `false`), with
        `undefined%` for the target, and **no recommendation and no disclaimer at
        all** — the one paragraph the module refuses to let the UI drop.
        """
        stub = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "assess_validity", "arguments": '
                        '{"subject": "cold storage robots", '
                        '"customer_download_confidence": 62, '
                        '"adobe_acceptance_confidence": 85, "reasoning": "r"}}</tool_call>',
                    )
                ],
                [("content", "Here is my verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stub)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        event = next(p for p in emitted if p["type"] == event_module.VALIDITY)
        payload = event["validity"]

        # 73.5 is below the 80 target, so the verdict must be an explicit False —
        # an absent key renders as a pass on the card.
        assert payload["collective_average"] == 73.5
        assert payload["meets_target"] is False
        assert payload["target_average"] == 80.0
        # The band is "strong" (that starts at 70) while the verdict is a miss —
        # which is precisely why `meets_target` exists and why the recommendation
        # is replaced for a below-target score. Rendering the band alone would call
        # a 73.5% idea a strong one.
        assert payload["collective_band"] == validity.BAND_STRONG
        assert payload["collective_label"]
        assert payload["recommendation"]
        assert payload["disclaimer"]
        # Below target, the recommendation must not read as a green light.
        assert "better idea" in payload["recommendation"]

    def test_a_score_above_the_target_reports_meets_target_true(self, monkeypatch):
        """The mirror, so the field cannot pass by always being False."""
        stub = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "assess_validity", "arguments": '
                        '{"subject": "cleanroom fabs", '
                        '"customer_download_confidence": 88, '
                        '"adobe_acceptance_confidence": 90, "reasoning": "r"}}</tool_call>',
                    )
                ],
                [("content", "Verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stub)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        payload = next(
            p for p in emitted if p["type"] == event_module.VALIDITY
        )["validity"]
        assert payload["meets_target"] is True
        assert "better idea" not in payload["recommendation"]

    def test_the_streamed_and_stored_validity_views_are_the_same_shape(
        self, monkeypatch
    ):
        """A field present in one and absent in the other is how the two views drifted.

        The card is rendered from the *event* while streaming and from the *stored
        result* after a reload, so any key only one of them carries produces a card
        that changes when the page is refreshed.
        """
        stub = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "assess_validity", "arguments": '
                        '{"subject": "cold storage robots", '
                        '"customer_download_confidence": 62, '
                        '"adobe_acceptance_confidence": 85, "reasoning": "r"}}</tool_call>',
                    )
                ],
                [("content", "Verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stub)
        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        streamed = next(p for p in emitted if p["type"] == event_module.VALIDITY)
        stored = result["validity"]
        assert set(streamed["validity"]) == set(stored)

    def test_the_offered_buttons_match_what_the_mode_can_deliver(self, monkeypatch):
        """An `ideas` run must not be offered a button that promises prompts.

        Keyed on the **mode**, not on this turn's `wants_prompts`: a gated
        research run also reports `wants_prompts` false, yet continuing is exactly
        what turns its prompts on. Reading `wants_prompts` here would have given
        every gated run the no-prompts wording and broken the Continue button that
        issue 01 was about.
        """
        def validity_call():
            return [
                (
                    "content",
                    '<tool_call>{"name": "assess_validity", "arguments": '
                    '{"subject": "cleanroom fabs", '
                    '"customer_download_confidence": 80, '
                    '"adobe_acceptance_confidence": 86, "reasoning": "r"}}</tool_call>',
                )
            ]

        for mode, expect_prompts in (("ideas", False), ("research", True)):
            stream = scripted_stream([validity_call(), [("content", "Verdict.")]])
            monkeypatch.setattr(agent, "stream_chat", stream)
            emitted, _ = agent.collect(
                agent.RunRequest(mode=mode, message="x", validity_check=True)
            )
            event = next(p for p in emitted if p["type"] == event_module.VALIDITY)
            continue_action = next(
                action
                for action in event["follow_up_actions"]
                if action["id"] == validity.CONTINUE_ACTION
            )
            promises_prompts = "prompt" in continue_action["message"].casefold()
            assert promises_prompts is expect_prompts, mode

    def test_the_system_prompt_carries_the_style_instruction_and_the_tools(
        self, monkeypatch
    ):
        """A stale tool list is how an agent calls a tool that no longer exists."""
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(
                mode="research",
                message="x",
                style_instruction="MY CUSTOM HOUSE STYLE",
                validity_check=True,
            )
        )
        system = stream.calls[0][0]["content"]
        assert "MY CUSTOM HOUSE STYLE" in system
        assert "web_search" in system
        assert "assess_validity" in system

    def test_the_priority_sources_reach_the_system_prompt(self, monkeypatch):
        """The uploaded list is only useful if the agent is actually told about it.

        `guidance()` is unit-tested in `test_research_sources.py`, but nothing
        asserted it was *wired in* — the whole feature is one keyword argument on
        `_initial_messages`, so dropping it would leave every test green while the
        operator's file silently did nothing.
        """
        from services.research import sources as sources_module

        source_set = sources_module.parse(
            {
                "sources": [
                    {
                        "url": "https://stock.adobe.com/search",
                        "name": "Adobe Stock search",
                        "priority": 1,
                    }
                ]
            }
        )
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(
                mode="research",
                message="x",
                validity_check=True,
                priority_sources=source_set,
            )
        )
        system = stream.calls[0][0]["content"]
        assert "stock.adobe.com" in system
        assert "site:" in system

    def test_no_priority_file_leaves_the_prompt_unchanged(self, monkeypatch):
        """The mirror: with no file the prompt must be byte-identical to before the
        feature existed, so an operator who never uploads one sees no change."""
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(agent.RunRequest(mode="research", message="x", validity_check=True))
        assert "site:" not in stream.calls[0][0]["content"]

    def test_the_validity_tool_is_not_advertised_when_the_check_is_off(
        self, monkeypatch
    ):
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=False)
        )
        system = stream.calls[0][0]["content"]
        assert "assess_validity" not in system

    def test_conversation_history_is_carried_into_the_next_turn(self, monkeypatch):
        """The operator says "continue with this idea" and the agent must know
        which idea that was."""
        stream = scripted_stream([[("content", "Answer.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(
                mode="research",
                message="continue",
                history=[
                    {"role": "user", "content": "automated warehouses"},
                    {"role": "assistant", "content": "Here is my verdict."},
                ],
            )
        )
        messages = stream.calls[0]
        contents = [str(message.get("content", "")) for message in messages]
        assert any("automated warehouses" in content for content in contents)
        assert any("Here is my verdict." in content for content in contents)


# --------------------------------------------------------------------------- #
# The event stream
# --------------------------------------------------------------------------- #

class TestEventStream:
    def test_sse_frames_are_single_line(self):
        """A raw newline in a payload would desynchronise the client's parser."""
        frame = event_module.sse_frame(
            event_module.event(event_module.MESSAGE, text="line one\nline two")
        )
        body = frame.split("data: ", 1)[1]
        assert body.count("\n") == 2  # the JSON newline is escaped; only framing remains

    def test_an_unknown_event_type_is_refused(self):
        with pytest.raises(ValueError):
            event_module.event("not_an_event")

    def test_a_payload_cannot_redefine_the_type(self):
        with pytest.raises(ValueError):
            event_module.event(event_module.MESSAGE, type="other")

    def test_sources_are_deduplicated_by_url(self):
        """One page returned by two queries must not look like two confirmations."""
        accumulator = event_module.EventAccumulator()
        accumulator.add(
            event_module.event(
                event_module.SOURCES,
                sources=[{"url": "https://a.com"}, {"url": "https://b.com"}],
            )
        )
        accumulator.add(
            event_module.event(
                event_module.SOURCES, sources=[{"url": "https://a.com"}]
            )
        )
        assert [source["url"] for source in accumulator.sources] == [
            "https://a.com",
            "https://b.com",
        ]

    def test_notices_are_deduplicated(self):
        accumulator = event_module.EventAccumulator()
        for _ in range(3):
            accumulator.add(event_module.event(event_module.NOTICE, text="same"))
        assert accumulator.notices == ["same"]

    def test_the_tool_summary_is_human_readable(self):
        assert "Searching the web" in event_module.summarise_tool_call(
            "web_search", {"query": "x"}
        )

    def test_a_context_event_is_part_of_the_vocabulary(self):
        """The live indicator has no other source of truth, so the type must be
        accepted by the framer."""
        payload = event_module.event(
            event_module.CONTEXT, used_tokens=10, window_tokens=100, level="ok"
        )
        assert payload["type"] == event_module.CONTEXT
        assert event_module.CONTEXT in event_module.ALL_TYPES

    def test_the_accumulator_keeps_the_latest_context_report(self):
        """Each report measures the conversation as it stands, so the last one
        describes the completed run."""
        accumulator = event_module.EventAccumulator()
        accumulator.add(
            event_module.event(event_module.CONTEXT, used_tokens=10, window_tokens=100)
        )
        accumulator.add(
            event_module.event(event_module.CONTEXT, used_tokens=90, window_tokens=100)
        )
        assert accumulator.context["used_tokens"] == 90

    def test_the_stored_context_report_has_no_type_key(self):
        """It is stored in a JSON column beside the other result fields, where a
        `type` discriminant would be misleading."""
        accumulator = event_module.EventAccumulator()
        accumulator.add(
            event_module.event(event_module.CONTEXT, used_tokens=10, window_tokens=100)
        )
        assert "type" not in accumulator.context


class TestTheValidityGateCanBeReleased:
    """The Continue button has to actually release the gate.

    Measured live: pressing "Continue with these confidence rates" sent the canned
    message, the run re-ran with the gate still on, `wants_prompts` stayed False, no
    ANSWER FORMAT block was substituted and the objective still said "Do NOT write
    the prompts yet" — so the operator received a second assessment instead of the
    prompts. That is the reported "the agent didn't provide the prompt at the end".
    """

    def test_the_continue_message_releases_the_gate(self):
        assert agent.RunRequest(
            mode="research", message="x", validity_check=True, released=True
        ).wants_prompts

    def test_a_gated_run_without_the_release_still_suppresses_prompts(self):
        assert not agent.RunRequest(
            mode="research", message="x", validity_check=True
        ).wants_prompts

    def test_ideas_never_want_prompts_even_when_released(self):
        """`ideas` proposes niches and stops; prompts would answer a question the
        operator did not ask."""
        assert not agent.RunRequest(
            mode="ideas", message="x", validity_check=True, released=True
        ).wants_prompts

    def test_the_released_objective_asks_for_prompts(self, monkeypatch):
        stream = scripted_stream([[("content", json_answer())]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(
                mode="research", message="continue", validity_check=True, released=True
            )
        )
        system = stream.calls[0][0]["content"]
        assert "Do NOT write the prompts yet" not in system
        assert "asked you to proceed" in system
        # And the JSON contract is actually described, not just referenced.
        assert "ANSWER FORMAT" in system

    def test_the_unreleased_objective_still_says_not_yet(self, monkeypatch):
        stream = scripted_stream([[("content", "A verdict.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        system = stream.calls[0][0]["content"]
        assert "Do NOT write the prompts yet" in system

    def test_the_released_run_offers_the_similarity_tool(self, monkeypatch):
        """The similarity tool is gated with prompts, so releasing must re-enable
        it or a released run could produce overlapping prompts silently."""
        stream = scripted_stream([[("content", json_answer())]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(
                mode="research", message="continue", validity_check=True, released=True
            )
        )
        assert "check_prompt_similarity" in stream.calls[0][0]["content"]


class TestTheToolBudgetBoundsResearchNotBookkeeping:
    """The budget must bound *work that can run away*, not the quality mechanism.

    Measured live: a gated run spent its 10th and final call on `assess_validity`,
    the loop then correctly judged the score below target and asked for a stronger
    candidate — with **zero calls left to look for one**. The budget intended to
    enable research was what starved it.
    """

    def test_a_validity_call_does_not_consume_the_budget(self, monkeypatch, stub_search):
        """The decisive case: bookkeeping must be free.

        With `max_tool_calls=2`, one research call plus one validity call leaves a
        research call still available. If validity were charged, the run would hit
        the cap and answer with what it had instead of looking further.
        """
        stub_search()
        stream = scripted_stream(
            [
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "q1"}}</tool_call>',
                    )
                ],
                [("content", self._score("idea", 50))],
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "q2"}}</tool_call>',
                    )
                ],
                [("content", "Verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True, max_tool_calls=2)
        )
        # Both research calls ran: the validity call between them was free.
        searches = [
            payload
            for payload in emitted
            if payload["type"] == event_module.TOOL_CALL and payload["name"] == "web_search"
        ]
        assert len(searches) == 2
        # And the budget was never reported as exhausted.
        assert not any(
            payload["type"] == event_module.NOTICE and "limit" in payload.get("text", "")
            for payload in emitted
        )

    def test_a_similarity_call_does_not_consume_the_budget(self, monkeypatch):
        """Same rule for the other bookkeeping tool, so neither can regress alone."""
        registry = tools.registry_for(wants_prompts=True, validity_check=False)
        assert registry["check_prompt_similarity"].consumes_budget is False
        assert registry["web_search"].consumes_budget is True
        assert registry["market_overview"].consumes_budget is True
        assert registry["fetch_page"].consumes_budget is True

    def test_the_validity_tool_is_marked_free(self):
        registry = tools.registry_for(wants_prompts=False, validity_check=True)
        assert registry["assess_validity"].consumes_budget is False

    def test_the_budget_still_bounds_research(self, monkeypatch, stub_search):
        """The mirror: exempting bookkeeping must not exempt real research.

        Without this, a change that made *every* tool free would leave the loop
        unbounded and still pass the tests above.
        """
        stub_search()
        counter = {"n": 0}

        def endless(messages, temperature=0.3, **kwargs):  # noqa: ANN001, ARG001
            counter["n"] += 1
            yield (
                "content",
                '<tool_call>{"name": "web_search", "arguments": {"query": "q'
                f'{counter["n"]}"}}}}</tool_call>',
            )

        monkeypatch.setattr(agent, "stream_chat", endless)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=3)
        )
        assert any(
            payload["type"] == event_module.NOTICE and "limit" in payload.get("text", "")
            for payload in emitted
        )

    def test_the_limit_notice_says_how_to_change_it(self, monkeypatch, stub_search):
        """`the agent reached its limit` is otherwise indistinguishable from a defect."""
        stub_search()
        stream = scripted_stream(
            [[("content", self._search_call(f"q{n}"))] for n in range(6)]
            + [[("content", "Done.")]]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=3)
        )
        notice = next(
            payload["text"]
            for payload in emitted
            if payload["type"] == event_module.NOTICE and "limit" in payload.get("text", "")
        )
        assert "3-call" in notice
        assert "Settings" in notice

    def test_the_default_budget_allows_a_real_investigation(self):
        """Ten was too small: `market_overview` alone spends three calls."""
        assert agent.DEFAULT_MAX_TOOL_CALLS >= 20
        assert agent.MIN_TOOL_CALLS < agent.DEFAULT_MAX_TOOL_CALLS < agent.MAX_TOOL_CALLS

    @staticmethod
    def _search_call(query: str) -> str:
        return (
            f'<tool_call>{{"name": "web_search", "arguments": {{"query": "{query}"}}}}</tool_call>'
        )

    @staticmethod
    def _score(subject: str, value: float) -> str:
        return (
            '<tool_call>{"name": "assess_validity", "arguments": {'
            f'"subject": "{subject}", "customer_download_confidence": {value}, '
            f'"adobe_acceptance_confidence": {value}, "reasoning": "r"}}}}</tool_call>'
        )


class TestTheAgentKeepsSearchingUntilTheTargetIsMet:
    """Finding a better idea is the point, so a below-target score is not an answer.

    Measured live: a run researched a replacement idea and returned **53%** — below
    the 72% of the idea the operator had just rejected — and presented it as the
    answer, because nothing in the loop compared the score to the target. The prompt
    asks the model to keep looking, but a prompt is a request, not a guarantee.
    """

    @staticmethod
    def _score(subject: str, value: float) -> str:
        return (
            '<tool_call>{"name": "assess_validity", "arguments": {"subject": "%s", '
            '"customer_download_confidence": %s, "adobe_acceptance_confidence": %s, '
            '"reasoning": "r"}}</tool_call>' % (subject, value, value)
        )

    def test_a_below_target_score_is_not_accepted_as_the_answer(self, monkeypatch):
        stream = scripted_stream(
            [
                [("content", self._score("weak idea", 50))],
                # The model tries to answer with the weak idea still standing.
                [("content", "Here is my verdict on the weak idea.")],
                # Nudged, it finds something better.
                [("content", self._score("strong idea", 90))],
                [("content", "Here is my verdict on the strong idea.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="find a better idea", validity_check=True)
        )
        assert any(
            p["type"] == event_module.NOTICE and "below the" in p.get("text", "")
            for p in emitted
        )
        # The nudge reached the model, naming the target.
        corrections = [
            str(message.get("content") or "")
            for call in stream.calls[2:]
            for message in call
            if message.get("role") == "user" and "target" in str(message.get("content"))
        ]
        assert corrections
        assert "80" in corrections[0]

    def test_the_nudge_is_bounded_so_a_stubborn_model_still_finishes(self, monkeypatch):
        """An unbounded search for an 80% idea would spend the whole budget."""
        script = [[("content", self._score(f"weak {index}", 40))] for index in range(6)]
        script.append([("content", "I could not find anything better.")])
        stream = scripted_stream(script)
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        nudges = [
            p
            for p in emitted
            if p["type"] == event_module.NOTICE and "below the" in p.get("text", "")
        ]
        assert len(nudges) <= agent.MAX_TARGET_ATTEMPTS
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_a_target_meeting_score_is_accepted_immediately(self, monkeypatch):
        stream = scripted_stream(
            [
                [("content", self._score("strong idea", 90))],
                [("content", "Here is my verdict.")],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        assert not any(
            p["type"] == event_module.NOTICE and "below the" in p.get("text", "")
            for p in emitted
        )

    def test_a_released_run_is_not_sent_back_to_research(self, monkeypatch):
        """A released run is writing prompts for an idea the operator accepted, so
        its score is no longer the deciding question."""
        stream = scripted_stream(
            [
                [("content", self._score("accepted idea", 45))],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(
                mode="research", message="continue", validity_check=True, released=True
            )
        )
        assert not any(
            p["type"] == event_module.NOTICE and "below the" in p.get("text", "")
            for p in emitted
        )

    def test_the_target_is_stated_in_the_objective(self, monkeypatch):
        stream = scripted_stream([[("content", "A verdict.")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        system = stream.calls[0][0]["content"]
        assert f"{validity.TARGET_AVERAGE:g}%" in system


class TestContextWindowInARun:
    def test_a_run_reports_its_context_position(self, monkeypatch):
        """The operator asked for a live indicator, which needs a measurement —
        and it must be emitted even for a short run, or the bar would only appear
        once a conversation was already long."""
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", "An answer.")]])
        )
        emitted, result = agent.collect(
            agent.RunRequest(mode="ideas", message="x", context_window=100_000)
        )
        reports = [p for p in emitted if p["type"] == event_module.CONTEXT]
        assert reports
        assert reports[0]["window_tokens"] == 100_000
        assert result["context"]["window_tokens"] == 100_000

    def test_the_report_is_measured_again_when_the_run_finishes(self, monkeypatch):
        """The first report describes the opening request; the last describes the
        request that was actually sent, tool results included."""
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", "An answer.")]])
        )
        emitted, _ = agent.collect(
            agent.RunRequest(mode="ideas", message="x", context_window=100_000)
        )
        reports = [p for p in emitted if p["type"] == event_module.CONTEXT]
        assert len(reports) >= 2

    def test_an_oversized_history_is_folded_before_it_is_sent(self, monkeypatch):
        """A conversation that overflows is truncated from the front by the
        provider, which removes the system prompt and leaves the model with no
        instructions — the failure that looks like a run stopping for no reason."""
        captured: list[list[dict]] = []

        def _stream(messages, temperature=0.3, **kwargs):  # noqa: ANN001, ARG001
            captured.append(list(messages))
            yield ("content", "An answer.")

        monkeypatch.setattr(agent, "stream_chat", _stream)
        monkeypatch.setattr(
            context_module, "summarise_turns", lambda *a, **k: ("COMPACTED DIGEST", "")
        )

        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 4000}
            for index in range(30)
        ]
        emitted, _ = agent.collect(
            agent.RunRequest(
                mode="ideas", message="new question", history=history, context_window=20_000
            )
        )

        sent = captured[0]
        # The system prompt survived, which is the whole point.
        assert sent[0]["role"] == "system"
        assert "You are a stock-photography research agent" in sent[0]["content"]
        # The digest replaced the older turns.
        assert any("COMPACTED DIGEST" in str(m.get("content")) for m in sent)
        # And the operator is told, rather than the run silently changing shape.
        assert any(
            p["type"] == event_module.NOTICE and "context window" in p.get("text", "")
            for p in emitted
        )

    def test_a_degraded_compaction_is_surfaced(self, monkeypatch):
        """A locally-excerpted digest is not a model summary, and the operator has
        to know that detail may be missing."""
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", "An answer.")]])
        )
        monkeypatch.setattr(
            context_module,
            "summarise_turns",
            lambda *a, **k: ("EXCERPT", "used a local excerpt instead"),
        )
        history = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 4000}
            for index in range(30)
        ]
        emitted, _ = agent.collect(
            agent.RunRequest(
                mode="ideas", message="q", history=history, context_window=20_000
            )
        )
        assert any(
            p["type"] == event_module.NOTICE and "local excerpt" in p.get("text", "")
            for p in emitted
        )

    def test_a_run_that_grows_past_the_window_compacts_mid_loop(
        self, monkeypatch, stub_search
    ):
        """Folding the stored history is only half the job.

        A single turn can add many large tool results, so a run that started inside
        the window can push itself out of it. Measured live before this was wired,
        the final report sat at **100% of the window**: the next request would have
        been truncated from the front, losing the system prompt. The observable
        claim is that a long-running loop keeps itself inside the window.
        """
        _install_huge_search(monkeypatch)
        monkeypatch.setattr(
            context_module, "summarise_turns", lambda *a, **k: ("LIVE DIGEST", "")
        )
        stream = scripted_stream(_tool_call_script(6) + [[("content", json_answer())]])
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(
                mode="research",
                message="warehouse robots",
                context_window=12_000,
                max_tool_calls=10,
            )
        )

        # It compacted, it said so, and it still finished normally.
        assert any(
            p["type"] == event_module.NOTICE
            and "grew past the context window" in p.get("text", "")
            for p in emitted
        )
        assert emitted[-1]["type"] == event_module.RUN_FINISHED
        assert result["context"]["compacted"] is True
        assert result["context"]["folded_turns"] > 0
        # The digest reached the model rather than being computed and dropped.
        assert any(
            "LIVE DIGEST" in str(message.get("content", ""))
            for call in stream.calls
            for message in call
        )

    def test_the_system_prompt_survives_in_run_compaction(
        self, monkeypatch, stub_search
    ):
        """The pinned system prompt is the whole reason folding exists: losing it
        leaves the model with no instructions and no output contract."""
        _install_huge_search(monkeypatch)
        monkeypatch.setattr(
            context_module, "summarise_turns", lambda *a, **k: ("LIVE DIGEST", "")
        )
        stream = scripted_stream(_tool_call_script(6) + [[("content", json_answer())]])
        monkeypatch.setattr(agent, "stream_chat", stream)

        agent.collect(
            agent.RunRequest(
                mode="research",
                message="warehouse robots",
                context_window=12_000,
                max_tool_calls=10,
            )
        )

        # Every request the agent sent still began with the system prompt.
        for call in stream.calls:
            assert call[0]["role"] == "system"
            assert "You are a stock-photography research agent" in call[0]["content"]

    def test_a_zero_window_never_compacts_a_run(self, monkeypatch, stub_search):
        """What a unit test wants, and what the default is when no window is
        configured: no summariser call, no surprise shape change."""
        _install_huge_search(monkeypatch)
        monkeypatch.setattr(
            context_module,
            "summarise_turns",
            lambda *a, **k: pytest.fail("must not be called"),
        )
        stream = scripted_stream(
            _tool_call_script(1) + [[("content", json_answer())]]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(
                mode="research", message="x", context_window=0, max_tool_calls=4
            )
        )
        assert result["context"]["compacted"] is False
        assert not any(
            p["type"] == event_module.NOTICE and "grew past" in p.get("text", "")
            for p in emitted
        )

    def test_a_zero_window_does_not_fold_anything(self, monkeypatch):
        """What a test wants by default: no summariser call, no surprise."""
        monkeypatch.setattr(
            agent, "stream_chat", scripted_stream([[("content", "An answer.")]])
        )
        monkeypatch.setattr(
            context_module, "summarise_turns", lambda *a, **k: pytest.fail("must not run")
        )
        history = [{"role": "user", "content": "x" * 100_000}]
        emitted, _ = agent.collect(
            agent.RunRequest(mode="ideas", message="q", history=history, context_window=0)
        )
        assert emitted[-1]["type"] == event_module.RUN_FINISHED


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

class TestPrompts:
    def test_the_default_style_is_the_operators_reference_prompt(self):
        """The reference is the standard generated prompts are measured against;
        paraphrasing it would change what the feature produces."""
        assert prompts.DEFAULT_STYLE_INSTRUCTION.startswith("Epic commercial stock photograph")
        assert prompts.DEFAULT_STYLE_INSTRUCTION.endswith("--ar 16:9")
        assert "20mm lens" in prompts.DEFAULT_STYLE_INSTRUCTION
        assert "f/6.3" in prompts.DEFAULT_STYLE_INSTRUCTION

    def test_house_rules_pin_the_16_9_ratio(self):
        assert "--ar 16:9" in prompts.HOUSE_RULES

    def test_house_rules_forbid_text_and_logos(self):
        assert "logos" in prompts.HOUSE_RULES
        assert "upscaling" in prompts.HOUSE_RULES

    def test_the_system_prompt_teaches_the_tool_call_format(self):
        """The parser's delimiter must not be a guess."""
        system = prompts.compose_system_prompt(
            tool_specs=tools.specs_for(wants_prompts=True, validity_check=False),
            style_instruction=prompts.DEFAULT_STYLE_INSTRUCTION,
            mode="batch",
            validity_check=False,
            max_tools=10,
        )
        assert protocol.TOOL_CALL_OPEN in system
        assert protocol.TOOL_CALL_CLOSE in system

    def test_the_system_prompt_forbids_inventing_evidence(self):
        system = prompts.compose_system_prompt(
            tool_specs=[],
            style_instruction="s",
            mode="research",
            validity_check=True,
            max_tools=5,
        )
        assert "Never invent tool output" in system
        assert "NEVER evidence" in system

    def test_the_objective_changes_with_the_mode(self):
        def system_for(mode: str, validity: bool) -> str:
            return prompts.compose_system_prompt(
                tool_specs=[],
                style_instruction="s",
                mode=mode,
                validity_check=validity,
                max_tools=5,
            )

        # With the validity check the agent must NOT write prompts yet.
        assert "Do NOT write the prompts yet" in system_for("research", True)
        assert "Do NOT write prompts" in system_for("ideas", False)
        # Without it, the prompts are the deliverable — but the niche is still
        # researched first so the prompts reflect what already exists.
        without_gate = system_for("research", False)
        assert "Research it with the tools" in without_gate
        assert "Do NOT write the prompts yet" not in without_gate

    def test_the_tool_list_is_generated_from_the_registry(self):
        """A tool cannot be added without the agent being told about it."""
        specs = tools.specs_for(wants_prompts=True, validity_check=True)
        rendered = prompts.tool_list_text(specs)
        for spec in specs:
            assert spec["name"] in rendered
