"""The blocked-fetch list — refusals before I/O, and priority pruning.

``fetch_page`` fails in ways retrying cannot fix (HTTP 403, timeout, anti-bot
page), and a model handed the same URL again will burn a tool call and the full
timeout to reach the identical failure. Two properties are asserted here rather
than the storage arithmetic:

* **The guard runs before any network I/O.** The no-I/O claim is *proved*, not
  assumed: ``fetch_page`` is replaced with a function that raises on call, so
  the test fails loudly if the guard ever moves behind the fetch.
* **A failure prunes the operator's priority list.** A source the agent can
  never read can only drag every future run's success rate down, so recording
  the failure and dropping the source happen together — and the model is told
  its set shrank.

Validation refusals (bad scheme, private host) are deliberately *not* blocked:
they were never attempted, so blocking them would refuse a URL the tool never
actually read.
"""

from __future__ import annotations

import json

from services.research import blocked_store, source_store, sources, tools


def _seed_sources(*urls: str) -> None:
    """Upload a priority-source file containing exactly ``urls``."""
    source_store.save(json.dumps({"version": 1, "sources": list(urls)}))


class TestBlockedStore:
    """The store's own contract: record, answer, release."""

    def test_a_failure_blocks_and_reports_the_error(self):
        blocked_store.add_failure("https://example.com/page", "HTTP 403")
        blocked, error = blocked_store.is_blocked("https://example.com/page")
        assert blocked is True
        assert error == "HTTP 403"

    def test_nothing_is_blocked_by_default(self):
        assert blocked_store.is_blocked("https://example.com/page") == (False, "")

    def test_a_repeat_failure_bumps_the_counter_in_place(self):
        """One row per page, with a count — the list answers "is this URL worth
        refusing", not "show me every attempt"."""
        blocked_store.add_failure("https://example.com/page", "HTTP 403")
        blocked_store.add_failure("https://example.com/page", "HTTP 403")
        entries = blocked_store.load()
        assert len(entries) == 1
        assert entries[0]["failures"] == 2
        assert entries[0]["error"] == "HTTP 403"
        assert entries[0]["host"] == "example.com"

    def test_new_failures_are_prepended(self):
        blocked_store.add_failure("https://older.example.com/", "timeout")
        blocked_store.add_failure("https://newer.example.com/", "HTTP 500")
        urls = [entry["url"] for entry in blocked_store.load()]
        assert urls == ["https://newer.example.com/", "https://older.example.com/"]

    def test_unblocking_releases_exactly_that_url(self):
        blocked_store.add_failure("https://a.example.com/", "HTTP 403")
        blocked_store.add_failure("https://b.example.com/", "HTTP 403")
        assert blocked_store.remove("https://a.example.com/") is True
        assert blocked_store.is_blocked("https://a.example.com/")[0] is False
        assert blocked_store.is_blocked("https://b.example.com/")[0] is True

    def test_removing_a_url_that_is_not_blocked_writes_nothing(self):
        assert blocked_store.remove("https://never-tried.example.com/") is False

    def test_clear_releases_everything(self):
        blocked_store.add_failure("https://a.example.com/", "HTTP 403")
        blocked_store.clear()
        assert blocked_store.load() == []
        assert blocked_store.is_blocked("https://a.example.com/")[0] is False

    def test_the_list_is_capped_at_the_newest_entries(self):
        """A deployment brushing against thousands of dead links must not grow
        an unreadable document; the newest failures are the ones worth showing."""
        for index in range(blocked_store.MAX_ENTRIES + 10):
            blocked_store.add_failure(f"https://site{index}.example.com/", "timeout")
        entries = blocked_store.load()
        assert len(entries) == blocked_store.MAX_ENTRIES
        # Head is the newest failure; the earliest ones were dropped.
        assert entries[0]["url"] == f"https://site{blocked_store.MAX_ENTRIES + 9}.example.com/"
        assert all(
            entry["url"] != "https://site0.example.com/" for entry in entries
        )

    def test_malformed_storage_reads_as_empty_rather_than_raising(self):
        """A corrupt record must never turn into a failed research run."""
        from services import app_settings

        document = app_settings.load_raw()
        document[blocked_store._STORE_KEY] = {"version": 1, "entries": "not a list"}
        app_settings.save_raw(document)
        assert blocked_store.load() == []
        assert blocked_store.is_blocked("https://example.com/")[0] is False


class TestKeyCanonicalisation:
    """``https://example.com`` and ``https://example.com/`` are one page."""

    def test_the_trailing_slash_variant_shares_one_key(self):
        assert sources.url_key("https://example.com") == sources.url_key(
            "https://example.com/"
        )

    def test_blocking_one_form_refuses_the_other(self):
        blocked_store.add_failure("https://example.com", "HTTP 403")
        blocked, error = blocked_store.is_blocked("https://example.com/")
        assert blocked is True
        assert error == "HTTP 403"

    def test_a_fragment_does_not_make_a_second_key(self):
        assert sources.url_key("https://example.com/page#a") == sources.url_key(
            "https://example.com/page#b"
        )

    def test_a_refused_url_still_gets_its_own_stable_key(self):
        """Unusable URLs must not all collapse into one key, or blocking a
        ``javascript:`` link would block every other malformed one too."""
        key = sources.url_key("javascript:alert(1)")
        assert key == "javascript:alert(1)"
        assert key != sources.url_key("not even close to a url")

    def test_a_url_urlparse_cannot_parse_does_not_raise(self):
        """An unterminated IPv6 bracket makes ``urlparse`` raise where
        ``normalise_url`` has no answer; the key must fall back instead of
        crashing the pre-call guard with ``ValueError``."""
        key = sources.url_key("https://[")
        assert key == "https://["
        assert blocked_store.is_blocked("https://[") == (False, "")


class TestTheGuardRefusesBeforeAnyNetworkIO:
    """The core claim: a blocked URL never reaches the network."""

    def test_the_guard_returns_without_calling_fetch_page(self, monkeypatch):
        blocked_store.add_failure("https://example.com/blocked", "HTTP 403")

        def _boom(url):  # noqa: ANN001
            raise AssertionError("network hit")

        # If the guard ever moves behind the fetch, this test fails loudly
        # instead of quietly making a request the feature exists to prevent.
        monkeypatch.setattr(tools.fetch_module, "fetch_page", _boom)

        outcome = tools._tool_fetch_page({"url": "https://example.com/blocked/"})

        assert outcome.degraded is True
        assert "blocked list" in outcome.text
        assert "HTTP 403" in outcome.text
        assert outcome.summary == "Blocked: previously failed"

    def test_an_unblocked_url_is_still_fetched(self, monkeypatch):
        """The guard must refuse *only* what is on the list."""
        seen: list[str] = []

        def _fetch(url):  # noqa: ANN001
            seen.append(url)
            return tools.fetch_module.PageContent(url=url, text="body", ok=True)

        monkeypatch.setattr(tools.fetch_module, "fetch_page", _fetch)
        outcome = tools._tool_fetch_page({"url": "https://example.com/open"})
        assert seen == ["https://example.com/open"]
        assert outcome.degraded is False


class TestAFailureIsRecordedAndPrunesThePriorityList:
    """Recording and pruning happen together, and the model is told."""

    def test_the_url_is_blocked_and_the_priority_source_is_removed(
        self, monkeypatch
    ):
        _seed_sources(
            "https://stock.adobe.com/search",
            "https://www.shutterstock.com/search",
        )
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url, ok=False, error="HTTP 403"
            ),
        )
        # The real ``is_fetchable`` resolves DNS to rule out private hosts;
        # stubbing only that decision keeps this test hermetic. The refusal
        # branch itself is pinned by the validation test below.
        monkeypatch.setattr(
            tools.fetch_module, "is_fetchable", lambda url: (True, "")
        )

        outcome = tools._tool_fetch_page(
            {"url": "https://stock.adobe.com/search"}
        )

        blocked, error = blocked_store.is_blocked("https://stock.adobe.com/search")
        assert blocked is True
        assert error == "HTTP 403"

        remaining = source_store.load()
        assert remaining is not None
        assert [s.url for s in remaining.sources] == [
            "https://www.shutterstock.com/search"
        ]

        assert outcome.degraded is True
        assert "blocked list" in outcome.text
        assert "priority sources" in outcome.text
        assert "removed from priority sources" in outcome.summary

    def test_a_failure_on_an_unlisted_url_blocks_without_touching_sources(
        self, monkeypatch
    ):
        _seed_sources("https://www.shutterstock.com/search")
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url, ok=False, error="the site served an anti-bot challenge page"
            ),
        )
        monkeypatch.setattr(
            tools.fetch_module, "is_fetchable", lambda url: (True, "")
        )

        outcome = tools._tool_fetch_page({"url": "https://news.example.com/story"})

        assert blocked_store.is_blocked("https://news.example.com/story")[0] is True
        # The list was never a match, so it must be untouched — not cleared.
        remaining = source_store.load()
        assert remaining is not None
        assert len(remaining.sources) == 1
        assert "priority sources" not in outcome.summary


class TestValidationRefusalsAreNotReadFailures:
    """A URL that was never attempted must never enter the blocked list."""

    def test_a_refused_scheme_does_not_block(self, monkeypatch):
        monkeypatch.setattr(
            tools.fetch_module,
            "fetch_page",
            lambda url: tools.fetch_module.PageContent(
                url=url,
                ok=False,
                error="only http/https URLs can be read (got 'javascript')",
            ),
        )
        # The REAL ``is_fetchable`` runs here: a bad scheme is decided before
        # any DNS lookup, so the test stays offline and exercises the exact
        # branch that keeps validation refusals out of the list.
        outcome = tools._tool_fetch_page({"url": "javascript:alert(1)"})

        assert outcome.degraded is True
        assert "Could not read" in outcome.summary
        assert "blocked" not in outcome.summary
        assert blocked_store.load() == []


class TestTheBlockedEndpoints:
    """The /prompts panel's HTTP surface, through the real router."""

    def test_an_empty_list_reads_as_empty(self, client):
        payload = client.get("/api/research/blocked").json()
        assert payload == {"entries": [], "total": 0}

    def test_a_stored_failure_is_listed_with_its_reason(self, client):
        blocked_store.add_failure("https://example.com/page", "HTTP 403")
        payload = client.get("/api/research/blocked").json()
        assert payload["total"] == 1
        entry = payload["entries"][0]
        assert entry["url"] == "https://example.com/page"
        assert entry["error"] == "HTTP 403"
        assert entry["failures"] == 1
        assert entry["blocked_at"]

    def test_deleting_one_url_releases_only_it(self, client):
        blocked_store.add_failure("https://a.example.com/", "HTTP 403")
        blocked_store.add_failure("https://b.example.com/", "timeout")
        response = client.delete(
            "/api/research/blocked", params={"url": "https://a.example.com/"}
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == 1
        assert payload["entries"][0]["url"] == "https://b.example.com/"
        assert blocked_store.is_blocked("https://a.example.com/")[0] is False

    def test_deleting_without_a_url_clears_the_list(self, client):
        blocked_store.add_failure("https://a.example.com/", "HTTP 403")
        blocked_store.add_failure("https://b.example.com/", "timeout")
        response = client.delete("/api/research/blocked")
        assert response.status_code == 200
        assert response.json() == {"entries": [], "total": 0}
        assert client.get("/api/research/blocked").json()["total"] == 0
