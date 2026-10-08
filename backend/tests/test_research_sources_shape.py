"""Source payloads reaching the event accumulator.

This module exists because of a crash that reached a live research run:

    AttributeError: 'str' object has no attribute 'get'

``_tool_fetch_page`` built ``sources`` as a **bare dict** — ``{"title", "url",
"snippet"}`` — while every other tool built a **list of dicts** and
``ToolOutcome.sources`` is annotated ``list[dict]``. Nothing caught it: a dict
and a one-element list are both perfectly ordinary values for a field nobody
type-checks at runtime.

The damage happened one layer away. ``EventAccumulator._merge_sources`` iterates
the payload, and iterating a dict yields its **keys** — so it called
``(source or {}).get("url")`` on the string ``"title"`` and raised. The run had
already spent several tool calls gathering real evidence; one malformed shape
threw all of it away.

Three properties are pinned here, and the ordering matters:

* **The tool returns the declared type.** Fixing the consumer alone would leave
  the bug latent, re-invented by the next tool author.
* **The accumulator survives a bad shape.** It is the one point every streamed
  event passes through, so it must not be the thing that ends a run.
* **The real tool works end to end.** The two tests above can both pass while
  ``fetch_page`` still emits the wrong shape; only this one exercises the path.
"""

from __future__ import annotations

import pytest

from services.research import events as event_module
from services.research import tools


class TestToolOutcomeNormalisesSources:
    """The boundary where a tool's slip is contained."""

    def test_a_list_of_dicts_is_unchanged(self):
        source = {"title": "t", "url": "u", "snippet": "s"}
        outcome = tools.ToolOutcome(text="", sources=[source])
        assert outcome.sources == [source]

    def test_a_bare_dict_is_promoted_to_one_source(self):
        """The defect itself. The author clearly meant one source, so the intent
        is honoured rather than the value discarded."""
        outcome = tools.ToolOutcome(
            text="", sources={"title": "t", "url": "u", "snippet": "s"}
        )
        assert outcome.sources == [{"title": "t", "url": "u", "snippet": "s"}]

    def test_none_becomes_an_empty_list(self):
        assert tools.ToolOutcome(text="", sources=None).sources == []

    def test_a_scalar_is_discarded_rather_than_crashing(self):
        assert tools.ToolOutcome(text="", sources="a title").sources == []

    def test_non_dict_entries_are_dropped(self):
        outcome = tools.ToolOutcome(
            text="", sources=[{"url": "u"}, "title", None, 7]
        )
        assert outcome.sources == [{"url": "u"}]

    def test_the_default_is_still_an_empty_list(self):
        assert tools.ToolOutcome(text="").sources == []


class TestTheAccumulatorSurvivesMalformedSources:
    """Defence in depth: the accumulator is the last thing before the store."""

    def _accumulate(self, payload) -> event_module.EventAccumulator:
        acc = event_module.EventAccumulator()
        acc.add({"type": "sources", "sources": payload})
        return acc

    def test_a_bare_dict_does_not_raise(self):
        """The regression test for the live crash."""
        acc = self._accumulate({"title": "t", "url": "u", "snippet": "s"})
        # A bare dict is not a list of sources, so nothing is claimed as a source;
        # what matters is that the call returns instead of raising.
        assert isinstance(acc.sources, list)

    @pytest.mark.parametrize(
        "payload",
        [
            ["title", "url", "snippet"],       # a dict's keys, as a list
            [None],
            ["just a string"],
            [("a", "b")],
            [7],
            None,
        ],
    )
    def test_no_shape_kills_the_run(self, payload):
        self._accumulate(payload)

    def test_good_sources_alongside_a_bad_one_still_land(self):
        """A malformed entry must not cost the run its real evidence."""
        acc = self._accumulate(
            [{"title": "t", "url": "u", "snippet": "s"}, "junk", None]
        )
        assert [s["url"] for s in acc.sources] == ["u"]

    def test_duplicate_urls_are_still_collapsed(self):
        """The de-duplication this method exists for must survive the guard."""
        acc = self._accumulate(
            [{"url": "u1"}, {"url": "u1"}, {"url": "u2"}]
        )
        assert [s["url"] for s in acc.sources] == ["u1", "u2"]

    def test_a_source_without_a_url_is_skipped(self):
        assert self._accumulate([{"title": "no url here"}]).sources == []


class TestFetchPageEmitsTheDeclaredShape:
    """The tool that caused the crash, checked through its own code path."""

    def test_a_successful_fetch_returns_a_list(self, monkeypatch):
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url,
                title="Example Domain",
                text="a page body",
                ok=True,
            ),
        )
        outcome = tools._tool_fetch_page({"url": "https://example.com/"})
        assert isinstance(outcome.sources, list)
        assert len(outcome.sources) == 1
        assert outcome.sources[0]["url"] == "https://example.com/"

    def test_a_failed_fetch_returns_no_sources(self, monkeypatch):
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url, title="", text="", ok=False, error="blocked"
            ),
        )
        outcome = tools._tool_fetch_page({"url": "https://example.com/"})
        assert outcome.sources == []
        assert outcome.degraded is True

    def test_the_outcome_survives_the_accumulator(self, monkeypatch):
        """End to end: the exact path that raised in production."""
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url, title="Example Domain", text="a page body", ok=True
            ),
        )
        outcome = tools._tool_fetch_page({"url": "https://example.com/"})
        acc = event_module.EventAccumulator()
        acc.add({"type": "sources", "sources": outcome.sources})
        assert len(acc.sources) == 1
        assert acc.sources[0]["url"] == "https://example.com/"


class TestTheOtherToolsAlreadyEmittedLists:
    """A guard against the next tool repeating the mistake.

    Every tool is invoked with stub arguments and its ``sources`` type checked,
    so a regression shows up as a failing test rather than as a live run.
    """

    def test_no_tool_emits_a_bare_dict(self):
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        sample_arguments = {
            "web_search": {"query": "logistics"},
            "fetch_page": {"url": "https://example.com/"},
            "market_overview": {"niche": "warehouse robots"},
            "assess_validity": {
                "subject": "warehouse robots",
                "customer_download_confidence": 80,
                "adobe_acceptance_confidence": 75,
            },
            "check_prompt_similarity": {"prompts": ["a", "b"]},
            "check_restrictions": {"metadata": {"title": "t", "description": "d"}},
            "list_categories": {},
        }
        checked = 0
        for name, tool in registry.items():
            arguments = sample_arguments.get(name)
            if arguments is None:
                continue
            outcome = tool.run(arguments)
            assert isinstance(outcome.sources, list), (
                f"tool {name!r} emitted {type(outcome.sources).__name__}, "
                "expected list"
            )
            assert all(isinstance(s, dict) for s in outcome.sources), (
                f"tool {name!r} emitted a non-dict source entry"
            )
            checked += 1
        # Every registered tool must be covered, so a NEW tool cannot slip in
        # unchecked - that is exactly how this defect shipped.
        assert checked == len(registry), (
            f"{len(registry) - checked} tool(s) unexercised: "
            f"{sorted(set(registry) - set(sample_arguments))}"
        )