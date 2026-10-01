"""The settings API surface for the web-search configuration.

Covers the HTTP contracts the Settings modal relies on:

* ``GET  /api/settings`` serves the resolved provider so the UI can show which
  search will actually run, rather than which one was merely requested.
* ``PUT  /api/settings`` applies a partial update and refuses a configuration
  that cannot work (Brave enabled with no key).
* ``POST /api/settings/test`` probes the search provider only when asked, and
  reports a failure as data rather than an HTTP error.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    """Point the settings store at a temp file so no real config is touched."""
    from config import settings

    monkeypatch.setattr(settings, "APP_SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(settings, "BRAVE_SEARCH_ENABLED", False)
    monkeypatch.setattr(settings, "BRAVE_SEARCH_API_KEY", "")
    return tmp_path / "settings.json"


def test_settings_serve_the_search_configuration(client, isolated_store):
    body = client.get("/api/settings").json()
    assert body["brave_search_enabled"] is False
    assert body["brave_search_api_key_set"] is False
    assert body["effective_search_provider"] == "duckduckgo"
    assert body["effective_uses_brave"] is False
    assert body["research_max_tool_calls"] > 10


def test_the_search_key_is_never_returned(client, isolated_store):
    client.put("/api/settings", json={"brave_search_api_key": "bsa-super-secret-value"})
    body = client.get("/api/settings").json()
    assert "bsa-super-secret-value" not in str(body)
    assert body["brave_search_api_key_set"] is True


def test_enabling_brave_switches_the_effective_provider(client, isolated_store):
    client.put("/api/settings", json={"brave_search_api_key": "k"})
    body = client.put("/api/settings", json={"brave_search_enabled": True}).json()
    assert body["effective_uses_brave"] is True
    assert body["effective_search_provider"] == "brave"


def test_enabling_brave_without_a_key_is_a_400(client, isolated_store):
    response = client.put("/api/settings", json={"brave_search_enabled": True})
    assert response.status_code == 400
    assert "API key" in response.json()["detail"]


def test_an_out_of_range_rate_is_a_400(client, isolated_store):
    response = client.put("/api/settings", json={"brave_search_rate_limit": 50})
    assert response.status_code == 400
    assert "rate limit" in response.json()["detail"]


def test_an_out_of_range_tool_budget_is_a_400(client, isolated_store):
    response = client.put("/api/settings", json={"research_max_tool_calls": 500})
    assert response.status_code == 400
    assert "tool limit" in response.json()["detail"]


def test_a_partial_update_leaves_the_search_key_alone(client, isolated_store):
    """The same contract the LLM key has: a save must not blank a credential."""
    client.put("/api/settings", json={"brave_search_api_key": "keep-me"})
    client.put("/api/settings", json={"research_max_tool_calls": 30})
    body = client.get("/api/settings").json()
    assert body["brave_search_api_key_set"] is True
    assert body["research_max_tool_calls"] == 30


def test_resetting_clears_the_search_settings(client, isolated_store):
    client.put(
        "/api/settings", json={"brave_search_api_key": "k", "brave_search_enabled": True}
    )
    body = client.post("/api/settings/reset").json()
    assert body["brave_search_enabled"] is False
    assert body["brave_search_api_key_set"] is False
    assert body["effective_search_provider"] == "duckduckgo"


# --------------------------------------------------------------------------- #
# The probe
# --------------------------------------------------------------------------- #

def test_a_plain_connection_test_does_not_probe_search(client, isolated_store, monkeypatch):
    """Checking the LLM endpoint must not spend a Brave query every time."""
    from services import llm_client
    from services.research import search as search_module

    monkeypatch.setattr(
        llm_client, "test_connection", lambda payload: {"ok": True, "model": "m"}
    )

    def _explode(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise AssertionError("search must not be probed unless asked")

    monkeypatch.setattr(search_module, "search", _explode)
    body = client.post("/api/settings/test", json={}).json()
    assert body["ok"] is True
    assert body.get("search") is None


def test_a_search_probe_reports_the_provider_that_answered(client, isolated_store, monkeypatch):
    from services import llm_client
    from services.research import search as search_module

    monkeypatch.setattr(
        llm_client, "test_connection", lambda payload: {"ok": True, "model": "m"}
    )
    monkeypatch.setattr(
        search_module,
        "search",
        lambda *a, **k: search_module.SearchResponse(
            query="q",
            results=[search_module.SearchResult(title="T", url="https://example.com")],
            provider="brave",
            provider_label="Brave Search",
        ),
    )
    body = client.post(
        "/api/settings/test", json={"probe_search": True, "brave_search_api_key": "k"}
    ).json()
    assert body["search"]["ok"] is True
    assert body["search"]["provider_label"] == "Brave Search"
    assert body["search"]["results"] == 1


def test_a_failed_search_probe_is_data_not_an_http_error(client, isolated_store, monkeypatch):
    """A bad search key is a normal state the modal renders inline."""
    from services import llm_client
    from services.research import search as search_module

    monkeypatch.setattr(
        llm_client, "test_connection", lambda payload: {"ok": True, "model": "m"}
    )
    monkeypatch.setattr(
        search_module,
        "search",
        lambda *a, **k: search_module.SearchResponse(
            query="q",
            ok=False,
            error="every search provider failed",
            provider_errors=["Brave Search: HTTP 401", "DuckDuckGo: blocked"],
        ),
    )
    response = client.post("/api/settings/test", json={"probe_search": True})
    assert response.status_code == 200
    body = response.json()
    assert body["search"]["ok"] is False
    assert "401" in body["search"]["error"]


def test_the_probe_does_not_persist_the_candidate_key(client, isolated_store, monkeypatch):
    """Testing a key the operator is still experimenting with must not pin it."""
    from services import llm_client
    from services.research import search as search_module

    monkeypatch.setattr(
        llm_client, "test_connection", lambda payload: {"ok": True, "model": "m"}
    )
    monkeypatch.setattr(
        search_module,
        "search",
        lambda *a, **k: search_module.SearchResponse(
            query="q",
            results=[search_module.SearchResult(title="T", url="https://example.com")],
            provider="brave",
            provider_label="Brave Search",
        ),
    )
    client.post(
        "/api/settings/test", json={"probe_search": True, "brave_search_api_key": "candidate"}
    )
    assert client.get("/api/settings").json()["brave_search_api_key_set"] is False
