"""Priority sources — the operator's own list of sites the agent should prefer.

The feature exists because the general search is a fallback chain and fails as a
unit: measured live, every query returned Google News coverage and the agent
reported "0 of 16 stock marketplaces", which reads as an empty market but is
really a search that never reached one.

Two properties are asserted here rather than the parsing arithmetic:

* **A bad file is refused with a reason.** A file that uploads and silently does
  nothing is indistinguishable from the feature being broken.
* **A good file changes the agent's behaviour.** Listing the sites is not enough —
  the prompt has to tell it to restrict its query and open the pages, because its
  default behaviour (search, read snippets, answer) is what misses them.
"""

from __future__ import annotations

import json

import pytest

from services.research import sources


class TestTheTemplateIsAWorkingExample:
    def test_the_template_parses(self):
        """A template that cannot be uploaded is not a specification.

        The operator asked to be able to download the exact format, and the point
        of a downloadable file is that it can be uploaded back unchanged.
        """
        parsed = sources.parse(sources.template())
        assert len(parsed.sources) >= 3

    def test_the_template_json_round_trips(self):
        parsed = sources.parse_text(sources.template_json())
        assert parsed.sources

    def test_the_template_includes_a_marketplace_and_a_policy_source(self):
        """The two kinds of evidence the agent actually needs: how crowded a niche
        is, and what Adobe will accept."""
        parsed = sources.parse(sources.template())
        tags = {tag for source in parsed.sources for tag in source.tags}
        assert "marketplace" in tags
        assert "policy" in tags


class TestAcceptedShapes:
    """A format that rejects the operator's first instinct is a format they will
    not use, so the documented object, a bare list and a single object all work."""

    def test_the_documented_object_shape(self):
        parsed = sources.parse(
            {"version": 1, "sources": [{"url": "https://stock.adobe.com/search"}]}
        )
        assert len(parsed.sources) == 1

    def test_a_bare_list_of_urls(self):
        parsed = sources.parse(["https://stock.adobe.com/search", "shutterstock.com"])
        assert len(parsed.sources) == 2

    def test_a_bare_list_of_objects(self):
        parsed = sources.parse([{"url": "https://stock.adobe.com/search", "name": "AS"}])
        assert parsed.sources[0].name == "AS"

    def test_a_single_source_object(self):
        parsed = sources.parse({"url": "https://stock.adobe.com/search"})
        assert len(parsed.sources) == 1

    def test_a_bare_host_gets_https(self):
        """Pasting a hostname is the most common thing to do."""
        parsed = sources.parse(["stock.adobe.com"])
        assert parsed.sources[0].url == "https://stock.adobe.com"

    def test_the_www_prefix_is_stripped_from_the_host(self):
        """The `site:` operator is more reliable without it, and two entries that
        differ only by `www.` are the same source."""
        parsed = sources.parse(["https://www.shutterstock.com/search"])
        assert parsed.sources[0].host == "shutterstock.com"

    def test_a_fragment_is_dropped(self):
        """It never changes what a fetch returns, and it makes two entries for one
        page look like two sources."""
        parsed = sources.parse(["https://stock.adobe.com/search#results"])
        assert "#" not in parsed.sources[0].url


class TestRejectionsAreExplained:
    def test_an_empty_file_is_refused_with_a_reason(self):
        with pytest.raises(sources.SourceFileError) as excinfo:
            sources.parse_text("")
        assert "empty" in str(excinfo.value).lower()

    def test_invalid_json_names_the_line_and_the_template(self):
        with pytest.raises(sources.SourceFileError) as excinfo:
            sources.parse_text('{"sources": [')
        message = str(excinfo.value)
        assert "JSON" in message
        assert "template" in message.lower()

    def test_a_file_with_no_usable_source_is_refused(self):
        with pytest.raises(sources.SourceFileError) as excinfo:
            sources.parse({"sources": []})
        assert "http" in str(excinfo.value)

    def test_a_non_url_entry_is_reported_rather_than_dropped_silently(self):
        with pytest.raises(sources.SourceFileError):
            sources.parse([{"name": "no url here"}])

    def test_a_javascript_url_is_refused(self):
        """A security boundary, not a formatting preference: these URLs are handed
        to the fetch tool."""
        with pytest.raises(sources.SourceFileError):
            sources.parse(["javascript:alert(1)"])

    def test_a_file_url_is_refused(self):
        with pytest.raises(sources.SourceFileError):
            sources.parse(["file:///etc/passwd"])

    def test_a_mixed_file_keeps_the_good_entries_and_warns_about_the_rest(self):
        """Dropping the whole file because one line is wrong would be hostile when
        the operator has twenty good sources."""
        parsed = sources.parse(
            [
                "https://stock.adobe.com/search",
                "not a url at all",
                "https://www.shutterstock.com/search",
            ]
        )
        assert len(parsed.sources) == 2
        assert parsed.warnings
        assert "skipped" in parsed.warnings[0]


class TestOrderingAndDeduplication:
    def test_sources_are_ordered_by_priority(self):
        parsed = sources.parse(
            [
                {"url": "https://c.example.com", "priority": 3},
                {"url": "https://a.example.com", "priority": 1},
                {"url": "https://b.example.com", "priority": 2},
            ]
        )
        assert [source.host for source in parsed.sources] == [
            "a.example.com",
            "b.example.com",
            "c.example.com",
        ]

    def test_the_same_url_twice_is_one_source(self):
        parsed = sources.parse(
            ["https://stock.adobe.com/search", "https://stock.adobe.com/search"]
        )
        assert len(parsed.sources) == 1

    def test_an_absurd_priority_is_clamped(self):
        parsed = sources.parse([{"url": "https://a.example.com", "priority": -5}])
        assert parsed.sources[0].priority == 1

    def test_a_non_numeric_priority_falls_back(self):
        parsed = sources.parse([{"url": "https://a.example.com", "priority": "high"}])
        assert parsed.sources[0].priority == 1

    def test_a_cap_is_applied_and_reported(self):
        many = [f"https://host{index}.example.com" for index in range(100)]
        parsed = sources.parse(many)
        assert len(parsed.sources) == sources.MAX_SOURCES
        assert any("ignored" in warning for warning in parsed.warnings)


class TestGuidanceTellsTheAgentWhatToDo:
    """Naming the sites is not enough. The agent's default behaviour — search, read
    the snippets, answer — is exactly what misses them, so the section has to state
    the behaviour it wants."""

    def test_no_sources_produces_no_section(self):
        """A run without a file must be byte-identical to one from before the
        feature existed."""
        assert sources.guidance(None) == ""
        assert sources.guidance(sources.SourceSet()) == ""

    def test_the_sites_are_listed(self):
        parsed = sources.parse(
            [{"url": "https://stock.adobe.com/search", "name": "Adobe Stock search"}]
        )
        text = sources.guidance(parsed)
        assert "Adobe Stock search" in text
        assert "stock.adobe.com" in text

    def test_it_asks_for_a_restricted_query(self):
        parsed = sources.parse(["https://stock.adobe.com/search"])
        text = sources.guidance(parsed)
        assert "site:" in text

    def test_it_asks_for_the_page_to_be_opened(self):
        """Catalogue counts live on the page, not in a search snippet."""
        parsed = sources.parse(["https://stock.adobe.com/search"])
        text = sources.guidance(parsed)
        assert "fetch_page" in text

    def test_it_says_an_unreachable_source_is_not_an_empty_one(self):
        """The failure this whole feature exists to prevent: a blocked search read
        as an absence of competition."""
        parsed = sources.parse(["https://stock.adobe.com/search"])
        text = sources.guidance(parsed)
        assert "not an empty one" in text

    def test_the_notes_are_carried_through(self):
        parsed = sources.parse(
            [
                {
                    "url": "https://stock.adobe.com/search",
                    "notes": "The header shows the catalogue count.",
                }
            ]
        )
        assert "The header shows the catalogue count." in sources.guidance(parsed)

    def test_the_section_is_bounded(self):
        """It goes into every request of the run."""
        many = [
            {
                "url": f"https://host{index}.example.com",
                "notes": "n" * sources.MAX_NOTES_CHARS,
            }
            for index in range(sources.MAX_SOURCES)
        ]
        text = sources.guidance(sources.parse(many))
        assert len(text) <= sources.MAX_RENDERED_CHARS + 60

    def test_hosts_are_distinct_and_ordered(self):
        parsed = sources.parse(
            [
                {"url": "https://b.example.com/one", "priority": 2},
                {"url": "https://a.example.com", "priority": 1},
                {"url": "https://b.example.com/two", "priority": 2},
            ]
        )
        assert parsed.hosts == ["a.example.com", "b.example.com"]


class TestRestrictedQueries:
    def test_a_query_variant_per_host(self):
        parsed = sources.parse(["https://stock.adobe.com/search", "shutterstock.com"])
        variants = sources.queries_for(parsed, "warehouse robots")
        # Both default to priority 1, so the order is the host order — asserted as a
        # set of the pairs rather than a sequence, because which host comes first is
        # an ordering detail and the *pairing* is the behaviour.
        assert set(variants) == {
            "warehouse robots site:stock.adobe.com",
            "warehouse robots site:shutterstock.com",
        }

    def test_a_higher_priority_source_comes_first(self):
        parsed = sources.parse(
            [
                {"url": "https://second.example.com", "priority": 2},
                {"url": "https://first.example.com", "priority": 1},
            ]
        )
        assert sources.queries_for(parsed, "q")[0].endswith("site:first.example.com")

    def test_no_sources_means_no_variants(self):
        assert sources.queries_for(None, "x") == []
        assert sources.queries_for(sources.SourceSet(), "x") == []

    def test_a_newline_in_a_query_is_stripped(self):
        """Or a query could smuggle a second one into the restricted expression."""
        assert "\n" not in sources.sanitise_query("a\nb")
