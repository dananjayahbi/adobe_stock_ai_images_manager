"""Brave search settings and the research tool budget.

These cover the *configuration* half of the two features: that a stored value is
read back, that a blank or masked key never blanks a working credential, that
enabling Brave without a key is refused rather than silently doing nothing, and
that the tool budget is resolved from settings rather than a constant.
"""

from __future__ import annotations

import pytest

from services import app_settings


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Redirect the settings store into a temp file, as the suite-wide fixture does.

    A local fixture so this file can be read on its own; the values never touch
    the developer's real ``storage/app_settings.json``.
    """
    path = tmp_path / "app_settings.json"
    monkeypatch.setattr(
        app_settings.settings, "APP_SETTINGS_PATH", path, raising=False
    )
    return path


# --------------------------------------------------------------------------- #
# Defaults — the feature must be invisible when unused
# --------------------------------------------------------------------------- #

def test_brave_is_off_until_the_operator_enables_it(store):
    config = app_settings.resolve_search()
    assert config.enabled is False
    assert config.uses_brave is False


def test_the_default_provider_is_duckduckgo(store):
    assert app_settings.read_public()["effective_search_provider"] == "duckduckgo"


def test_a_stored_key_without_enabling_it_is_not_used(store):
    app_settings.update({"brave_search_api_key": "brave-key"})
    config = app_settings.resolve_search()
    assert config.has_api_key is True
    # Stored but not enabled: the operator saved a key, not a decision.
    assert config.enabled is False
    assert config.uses_brave is False


def test_enabling_with_a_key_makes_brave_effective(store):
    app_settings.update({"brave_search_api_key": "brave-key"})
    public = app_settings.update({"brave_search_enabled": True})
    assert public["brave_search_enabled"] is True
    assert public["effective_uses_brave"] is True
    assert public["effective_search_provider"] == "brave"


# --------------------------------------------------------------------------- #
# The key contract — same rules as the LLM credential
# --------------------------------------------------------------------------- #

def test_the_key_is_never_returned_in_a_usable_form(store):
    app_settings.update({"brave_search_api_key": "super-secret-brave-key"})
    public = app_settings.read_public()
    assert "super-secret-brave-key" not in str(public)
    assert public["brave_search_api_key_set"] is True
    assert public["brave_search_api_key_masked"].startswith("brave:")


def test_a_blank_key_keeps_the_stored_one(store):
    app_settings.update({"brave_search_api_key": "original-key"})
    app_settings.update({"brave_search_api_key": ""})
    assert app_settings.resolve_search().api_key == "original-key"


def test_the_mask_keeps_the_stored_key(store):
    """A UI that round-trips the mask must not blank a working credential."""
    app_settings.update({"brave_search_api_key": "original-key"})
    mask = app_settings.read_public()["brave_search_api_key_masked"]
    app_settings.update({"brave_search_api_key": mask})
    assert app_settings.resolve_search().api_key == "original-key"


def test_clearing_removes_the_key_so_the_environment_is_reachable_again(store):
    app_settings.update({"brave_search_api_key": "original-key"})
    app_settings.update({"clear_brave_search_key": True})
    assert app_settings.resolve_search().api_key == ""


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def test_enabling_without_any_key_is_refused(store):
    """A configuration that looks enabled and silently is not is worse than a refusal."""
    with pytest.raises(app_settings.SettingsValidationError) as excinfo:
        app_settings.update({"brave_search_enabled": True})
    assert "API key" in str(excinfo.value)


def test_enabling_with_a_key_in_the_same_payload_is_allowed(store):
    public = app_settings.update(
        {"brave_search_api_key": "k", "brave_search_enabled": True}
    )
    assert public["effective_uses_brave"] is True


def test_enabling_is_allowed_when_a_key_is_already_stored(store):
    app_settings.update({"brave_search_api_key": "k"})
    public = app_settings.update({"brave_search_enabled": True})
    assert public["effective_uses_brave"] is True


def test_an_out_of_range_rate_is_refused_not_clamped(store):
    """Clamping would silently change how long every research run takes."""
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"brave_search_rate_limit": 99})
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"brave_search_rate_limit": 0})


def test_a_valid_rate_is_stored_and_returned(store):
    public = app_settings.update({"brave_search_rate_limit": 2.5})
    assert public["brave_search_rate_limit"] == 2.5


def test_a_non_numeric_rate_is_refused(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"brave_search_rate_limit": "fast"})


def test_the_bounds_are_served_so_the_ui_can_validate_locally(store):
    bounds = app_settings.read_public()["bounds"]
    assert bounds["min_brave_rate"] == app_settings.MIN_BRAVE_RATE
    assert bounds["max_brave_rate"] == app_settings.MAX_BRAVE_RATE
    assert bounds["min_tool_calls"] == app_settings.MIN_TOOL_CALLS
    assert bounds["max_tool_calls"] == app_settings.MAX_TOOL_CALLS


# --------------------------------------------------------------------------- #
# The research tool budget
# --------------------------------------------------------------------------- #

def test_the_budget_defaults_to_the_module_constant(store):
    from services.research import agent

    assert app_settings.resolve_tool_budget() == agent.DEFAULT_MAX_TOOL_CALLS


def test_the_default_budget_is_larger_than_the_old_hard_cap(store):
    """Ten was measurably too small: `market_overview` spends three calls each.

    A run that checked two candidates for saturation and fetched one page had
    already spent eight before scoring anything.
    """
    from services.research import agent

    assert agent.DEFAULT_MAX_TOOL_CALLS > 10


def test_a_stored_budget_is_used(store):
    app_settings.update({"research_max_tool_calls": 40})
    assert app_settings.resolve_tool_budget() == 40


def test_an_out_of_range_budget_is_refused(store):
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"research_max_tool_calls": 1000})
    with pytest.raises(app_settings.SettingsValidationError):
        app_settings.update({"research_max_tool_calls": 1})


def test_a_hand_edited_out_of_range_budget_falls_back_instead_of_raising(store):
    """A read path must not raise: one bad value would break every research run."""
    from services.research import agent

    app_settings.save_raw({"research_max_tool_calls": 9999})
    assert app_settings.resolve_tool_budget() == agent.DEFAULT_MAX_TOOL_CALLS


def test_reset_clears_the_search_settings_too(store):
    app_settings.update({"brave_search_api_key": "k", "brave_search_enabled": True})
    app_settings.save_raw({})
    config = app_settings.resolve_search()
    assert config.enabled is False
    assert config.api_key == ""
