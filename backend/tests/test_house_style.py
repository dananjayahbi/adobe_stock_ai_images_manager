"""The house style and house rules — the operator's saved standard.

The bug this module exists to close: the style instruction was React state seeded
from a module constant and discarded on reload, so an operator who wrote their
house standard lost it on every refresh. It was persisted only as a side effect
of *starting a run*, which is why editing it without running looked like it had
no effect at all.

The properties asserted here are therefore about **round-tripping and
authority**, not about the text itself:

* **A saved edit comes back.** Read it through the API, not through the module,
  because the page reloads from the endpoint and a module-level test would pass
  while the endpoint served the constant.
* **The saved text is what the model reads.** If the system prompt were still
  built from `prompts.HOUSE_RULES`, the editor would be a convincing lie.
* **Clearing restores the shipped default**, and a partial edit leaves the other
  field alone.
* **A rejected value changes nothing at all** — no half-applied standard.
"""

from __future__ import annotations

import pytest

from services import app_settings
from services.research import house_style, prompts, tools
from services.research.agent import RunRequest


class TestDefaultsWhenNothingIsSaved:
    def test_a_fresh_install_reports_the_shipped_defaults(self):
        loaded = house_style.load()
        assert loaded.style_instruction == prompts.DEFAULT_STYLE_INSTRUCTION
        assert loaded.house_rules == prompts.HOUSE_RULES

    def test_nothing_is_reported_as_custom_before_any_edit(self):
        loaded = house_style.load()
        assert loaded.style_is_custom is False
        assert loaded.rules_is_custom is False

    def test_a_corrupt_store_does_not_raise_on_a_read_path(self):
        """A hand-edited file must degrade to the defaults, not 500 every run."""
        app_settings.save_raw(
            {"house_style_instruction": {"not": "a string"}, "house_rules": 17}
        )
        loaded = house_style.load()
        assert loaded.style_instruction == prompts.DEFAULT_STYLE_INSTRUCTION
        assert loaded.house_rules == prompts.HOUSE_RULES


class TestRoundTrip:
    def test_a_saved_style_comes_back(self):
        house_style.save(style_instruction="MY HOUSE STYLE")
        assert house_style.load().style_instruction == "MY HOUSE STYLE"

    def test_a_saved_rules_block_comes_back(self):
        house_style.save(house_rules="- Always 4:5 vertical.")
        assert house_style.load().house_rules == "- Always 4:5 vertical."

    def test_a_saved_field_is_reported_as_custom(self):
        house_style.save(style_instruction="mine")
        loaded = house_style.load()
        assert loaded.style_is_custom is True
        assert loaded.rules_is_custom is False

    def test_whitespace_is_stripped_so_the_dirty_check_means_something(self):
        """A textarea emits a trailing newline; storing it would report the box
        as modified forever."""
        house_style.save(style_instruction="  mine  \n")
        assert house_style.load().style_instruction == "mine"

    def test_an_omitted_field_is_left_alone(self):
        """The dangerous regression: saving one field wiping the other."""
        house_style.save(style_instruction="style A", house_rules="rules B")
        house_style.save(style_instruction="style A2")
        loaded = house_style.load()
        assert loaded.style_instruction == "style A2"
        assert loaded.house_rules == "rules B"

    def test_a_saved_edit_survives_a_reload_of_the_store(self):
        """Read through the document, not through a cached dataclass."""
        house_style.save(style_instruction="persisted")
        assert app_settings.load_raw()["house_style_instruction"] == "persisted"


class TestClearingRestoresTheDefault:
    def test_a_blank_style_restores_the_shipped_default(self):
        house_style.save(style_instruction="mine")
        house_style.save(style_instruction="")
        loaded = house_style.load()
        assert loaded.style_instruction == prompts.DEFAULT_STYLE_INSTRUCTION
        assert loaded.style_is_custom is False

    def test_a_blank_rules_block_restores_the_shipped_default(self):
        house_style.save(house_rules="mine")
        house_style.save(house_rules="")
        loaded = house_style.load()
        assert loaded.house_rules == prompts.HOUSE_RULES
        assert loaded.rules_is_custom is False

    def test_the_key_is_removed_rather_than_stored_as_a_blank(self):
        """so the document returns to its pre-edit state, not to a meaningless
        empty string that later code has to keep special-casing."""
        house_style.save(style_instruction="mine")
        house_style.save(style_instruction="")
        assert "house_style_instruction" not in app_settings.load_raw()

    def test_reset_clears_both_fields(self):
        house_style.save(style_instruction="a", house_rules="b")
        loaded = house_style.reset(style_instruction=True, house_rules=True)
        assert loaded.style_instruction == prompts.DEFAULT_STYLE_INSTRUCTION
        assert loaded.house_rules == prompts.HOUSE_RULES


class TestValidation:
    def test_an_over_long_style_is_refused_with_the_limit(self):
        with pytest.raises(house_style.HouseStyleError) as excinfo:
            house_style.save(style_instruction="x" * (house_style.MAX_STYLE_CHARS + 1))
        assert "8,000" in str(excinfo.value)

    def test_an_over_long_rules_block_is_refused(self):
        with pytest.raises(house_style.HouseStyleError):
            house_style.save(house_rules="x" * (house_style.MAX_RULES_CHARS + 1))

    def test_a_rejected_update_leaves_the_previous_value_intact(self):
        """Both fields are validated before either is written, so a rejection
        cannot leave a half-applied standard."""
        house_style.save(style_instruction="keep me", house_rules="keep me too")
        with pytest.raises(house_style.HouseStyleError):
            house_style.save(
                style_instruction="this one is fine",
                house_rules="x" * (house_style.MAX_RULES_CHARS + 1),
            )
        loaded = house_style.load()
        assert loaded.style_instruction == "keep me"
        assert loaded.house_rules == "keep me too"


class TestTheSystemPromptUsesTheSavedText:
    """The point of the whole feature: the text the operator edited must be the
    text the model reads. A prompt still built from the module constant would
    leave a fully working editor that changes nothing."""

    def _system(self, **kwargs) -> str:
        return prompts.compose_system_prompt(
            tool_specs=tools.specs_for(wants_prompts=True, validity_check=False),
            mode="batch",
            validity_check=False,
            max_tools=10,
            **kwargs,
        )

    def test_saved_rules_reach_the_system_prompt(self):
        house_style.save(house_rules="- MY OWN RULE: always shoot at dawn.")
        system = self._system(
            style_instruction=house_style.effective_style(),
            house_rules=house_style.effective_rules(),
        )
        assert "- MY OWN RULE: always shoot at dawn." in system

    def test_the_shipped_rules_are_absent_once_overridden(self):
        house_style.save(house_rules="- ONLY THIS.")
        system = self._system(
            style_instruction=house_style.effective_style(),
            house_rules=house_style.effective_rules(),
        )
        assert prompts.HOUSE_RULES not in system

    def test_omitting_house_rules_falls_back_to_the_shipped_default(self):
        """Keeps every existing caller and test working unchanged."""
        system = self._system(style_instruction="s", house_rules="")
        assert prompts.HOUSE_RULES in system

    def test_a_run_reaches_the_agent_with_the_saved_rules(self):
        """End to end through the agent, not just the prompt builder."""
        house_style.save(house_rules="- THE AGENT MUST SEE THIS.")
        system = _system_for_agent(house_style.effective_rules())
        assert "- THE AGENT MUST SEE THIS." in system


def _system_for_agent(house_rules: str) -> str:
    """The system prompt an actual run would build, via the agent's own path."""
    from services.research import agent as agent_module

    request = RunRequest(
        mode="batch",
        message="warehouses",
        style_instruction=house_style.effective_style(),
        house_rules=house_rules,
    )
    messages, _folded = agent_module._initial_messages(request, tools.specs_for(
        wants_prompts=True, validity_check=False
    ))
    return messages[0]["content"]


class TestTheRunRequestCarriesTheRules:
    def test_a_run_request_accepts_house_rules(self):
        request = RunRequest(mode="static", message="x", house_rules="rules")
        assert request.house_rules == "rules"

    def test_the_default_is_empty_so_the_constant_is_used(self):
        assert RunRequest(mode="static", message="x").house_rules == ""


class TestTheEndpoints:
    """Through the HTTP layer, because that is what the page reloads from.

    A module-level round trip would pass even if the endpoint still served the
    constant — which is precisely the shape the original bug had.
    """

    def test_get_reports_the_shipped_defaults_on_a_fresh_install(self, client):
        payload = client.get("/api/research/style").json()
        assert payload["style_instruction"] == prompts.DEFAULT_STYLE_INSTRUCTION
        assert payload["house_rules"] == prompts.HOUSE_RULES
        assert payload["style_is_custom"] is False

    def test_a_saved_style_is_served_after_a_reload(self, client):
        """The regression itself: edit, re-fetch, still there."""
        client.put("/api/research/style", json={"style_instruction": "MY STYLE"})
        reloaded = client.get("/api/research/style").json()
        assert reloaded["style_instruction"] == "MY STYLE"
        assert reloaded["style_is_custom"] is True

    def test_a_saved_rules_block_is_served_after_a_reload(self, client):
        client.put("/api/research/style", json={"house_rules": "- ONLY 4:5."})
        reloaded = client.get("/api/research/style").json()
        assert reloaded["house_rules"] == "- ONLY 4:5."
        assert reloaded["rules_is_custom"] is True

    def test_the_page_settings_endpoint_serves_the_saved_style(self, client):
        """The research page seeds from here, not from the style endpoint."""
        client.put("/api/research/style", json={"style_instruction": "SAVED STYLE"})
        payload = client.get("/api/research/settings").json()
        assert payload["default_style_instruction"] == "SAVED STYLE"

    def test_the_page_settings_endpoint_serves_the_saved_rules(self, client):
        client.put("/api/research/style", json={"house_rules": "- SAVED RULES."})
        payload = client.get("/api/research/settings").json()
        assert payload["house_rules"] == "- SAVED RULES."

    def test_a_partial_save_leaves_the_other_field_alone(self, client):
        client.put(
            "/api/research/style",
            json={"style_instruction": "style A", "house_rules": "rules B"},
        )
        client.put("/api/research/style", json={"house_rules": "rules B2"})
        payload = client.get("/api/research/style").json()
        assert payload["style_instruction"] == "style A"
        assert payload["house_rules"] == "rules B2"

    def test_a_blank_value_restores_the_default_through_the_endpoint(self, client):
        client.put("/api/research/style", json={"style_instruction": "mine"})
        payload = client.put(
            "/api/research/style", json={"style_instruction": ""}
        ).json()
        assert payload["style_instruction"] == prompts.DEFAULT_STYLE_INSTRUCTION
        assert payload["style_is_custom"] is False

    def test_delete_restores_both_defaults(self, client):
        client.put(
            "/api/research/style",
            json={"style_instruction": "a", "house_rules": "b"},
        )
        payload = client.delete("/api/research/style").json()
        assert payload["style_instruction"] == prompts.DEFAULT_STYLE_INSTRUCTION
        assert payload["house_rules"] == prompts.HOUSE_RULES
        assert payload["style_is_custom"] is False
        assert payload["rules_is_custom"] is False

    def test_an_over_long_value_is_refused_with_a_400_and_the_reason(self, client):
        response = client.put(
            "/api/research/style",
            json={"style_instruction": "x" * (house_style.MAX_STYLE_CHARS + 1)},
        )
        assert response.status_code == 400
        assert "8,000" in response.json()["detail"]

    def test_a_refused_save_changes_nothing(self, client):
        client.put("/api/research/style", json={"style_instruction": "keep me"})
        client.put(
            "/api/research/style",
            json={"house_rules": "x" * (house_style.MAX_RULES_CHARS + 1)},
        )
        payload = client.get("/api/research/style").json()
        assert payload["style_instruction"] == "keep me"