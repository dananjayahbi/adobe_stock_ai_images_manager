"""Per-mode system prompts, the merged generate mode, and library search.

What is pinned here:

* **The operator's text is what the model reads.** A saved prompt must reach
  ``compose_system_prompt`` — an editor that saves into a store the composer
  never reads is a convincing lie (the same defect class as the old house-style
  round trip).
* **Raw paste, no substitution.** The operator pastes one plain text per mode;
  it lands in the system prompt verbatim — braces, JSON examples and all.
  Nothing in the box is a placeholder.
* **Reset-by-clearing**: empty text restores the shipped default and flips
  ``is_custom`` back to False.
* **Three modes, legacy ids accepted**: ``generate`` replaces ``static``/
  ``batch`` on the wire, but old ids still create runs.
* **Search composes with the status tabs** and an empty query matches
  everything.
"""

from __future__ import annotations

import pytest

from services import prompt_library
from services.research import agent as agent_module
from services.research import events as event_module
from services.research import prompts, synthesis, system_prompts


@pytest.fixture()
def stub_agent(monkeypatch):
    """Replace the agent with a trivial completed run (same shape as the
    research API tests use — patching `agent.run` keeps request handling real)."""

    def _install(events=None, answer="Here is my answer."):
        scripted = events if events is not None else [
            event_module.event(event_module.RUN_STARTED, mode="generate"),
            event_module.event(event_module.MESSAGE, text=answer),
            event_module.event(
                event_module.RUN_FINISHED, status="completed", answer=answer
            ),
        ]

        def _run(request):  # noqa: ANN001
            for payload in scripted:
                yield payload

        monkeypatch.setattr(agent_module, "run", _run)
        return scripted

    return _install


class TestDefaults:
    def test_all_three_modes_serve_the_shipped_default(self, client):
        payload = client.get("/api/research/system-prompts").json()
        assert set(payload["items"]) == {"research", "ideas", "generate"}
        default = system_prompts.default_template()
        assert payload["items"]["research"] == default
        assert payload["is_custom"] == {
            "research": False,
            "ideas": False,
            "generate": False,
        }

    def test_the_default_is_the_shipped_style_block(self):
        """House style merged into the system prompt: the default text is the
        old style note + style instruction + house rules, verbatim."""
        text = system_prompts.default_template()
        assert "house standard" in text
        assert "STYLE INSTRUCTION" in text
        assert "--ar 16:9" in text
        # No placeholder tokens anywhere.
        assert "{" not in text

    def test_placeholders_are_not_served_there_are_none(self, client):
        payload = client.get("/api/research/system-prompts").json()
        assert "placeholders" not in payload

    def test_legacy_modes_map_to_generate(self):
        assert system_prompts.key_for("static") == "generate"
        assert system_prompts.key_for("batch") == "generate"
        assert system_prompts.key_for("ideas") == "ideas"


class TestRoundTrip:
    def test_a_saved_prompt_comes_back_and_is_marked_custom(self, client):
        payload = client.put(
            "/api/research/system-prompts",
            json={"mode": "research", "text": "MY RESEARCH TEMPLATE"},
        ).json()
        assert payload["items"]["research"] == "MY RESEARCH TEMPLATE"
        assert payload["is_custom"]["research"] is True
        # One mode's edit leaves the others alone.
        assert payload["is_custom"]["ideas"] is False

        reloaded = client.get("/api/research/system-prompts").json()
        assert reloaded["items"]["research"] == "MY RESEARCH TEMPLATE"

    def test_empty_text_restores_the_default(self, client):
        client.put(
            "/api/research/system-prompts",
            json={"mode": "generate", "text": "mine"},
        )
        payload = client.put(
            "/api/research/system-prompts",
            json={"mode": "generate", "text": ""},
        ).json()
        assert payload["items"]["generate"] == system_prompts.default_template()
        assert payload["is_custom"]["generate"] is False

    def test_an_unknown_mode_is_a_400(self, client):
        response = client.put(
            "/api/research/system-prompts",
            json={"mode": "nonsense", "text": "x"},
        )
        assert response.status_code == 400
        assert "research" in response.json()["detail"]

    def test_the_composer_appends_the_saved_text_verbatim(self):
        """The whole point: saved text must reach the system prompt untouched."""
        system_prompts.save("generate", "MY TEMPLATE\nMY RULES")
        composed = prompts.compose_system_prompt(
            tool_specs=[],
            mode="generate",
            validity_check=False,
            max_tools=7,
        )
        assert "MY TEMPLATE\nMY RULES" in composed
        # The runtime section above it is still assembled by the composer.
        assert "OBJECTIVE FOR THIS RUN" in composed

    def test_literal_json_braces_in_saved_text_survive(self):
        """No substitution at all: a pasted JSON example in the operator's text
        must not raise or get mangled."""
        system_prompts.save(
            "research", 'Answer like {"name": "x"} — then stop'
        )
        composed = prompts.compose_system_prompt(
            tool_specs=[],
            mode="research",
            validity_check=False,
            max_tools=5,
        )
        assert '{"name": "x"}' in composed

    def test_an_empty_source_section_does_not_leave_a_gap(self):
        """No priority sources → the budget line and the operator's text join
        cleanly, with no empty paragraph between them."""
        composed = prompts.compose_system_prompt(
            tool_specs=[],
            mode="generate",
            validity_check=False,
            max_tools=5,
            source_guidance="",
        )
        body = composed.split("OBJECTIVE FOR THIS RUN", 1)[1]
        assert "\n\n\n" not in body

    def test_priority_sources_reach_the_system_prompt(self):
        """An uploaded source file must be injected regardless of what text the
        operator keeps in their system prompt — it is their own data."""
        system_prompts.save("research", "JUST CONTENT GUIDANCE")
        composed = prompts.compose_system_prompt(
            tool_specs=[],
            mode="research",
            validity_check=False,
            max_tools=5,
            source_guidance="PRIORITY SOURCES\n- https://example.com",
        )
        assert "PRIORITY SOURCES" in composed
        assert "JUST CONTENT GUIDANCE" in composed


class TestAspectRatioFollowsTheSystemPrompt:
    """The operator's system prompt is the only authority on the ratio.

    The runtime used to hardcode ``--ar 16:9`` into the answer contract and the
    validation warnings, so a House Standard saying ``1:1`` was overridden. The
    token is now *read from* the saved text.
    """

    def test_the_token_is_read_from_the_saved_prompt(self):
        system_prompts.save("generate", "Every prompt must end with --ar 1:1.")
        assert prompts.aspect_token_for("generate") == "--ar 1:1"

    def test_a_prompt_without_a_token_imposes_none(self):
        system_prompts.save("generate", "Pure white background, no ratio set.")
        assert prompts.aspect_token_for("generate") is None

    def test_an_untouched_install_falls_back_to_the_shipped_default(self):
        assert prompts.aspect_token_for("generate") == synthesis.ASPECT_TOKEN

    def test_legacy_modes_resolve_the_generate_prompt(self):
        system_prompts.save("generate", "Always end with --ar 4:5.")
        assert prompts.aspect_token_for("static") == "--ar 4:5"
        assert prompts.aspect_token_for("batch") == "--ar 4:5"

    def test_the_answer_format_carries_the_saved_ratio_only(self):
        system_prompts.save("generate", "Always --ar 1:1. Never another ratio.")
        composed = prompts.compose_system_prompt(
            tool_specs=[],
            mode="generate",
            validity_check=False,
            max_tools=5,
        )
        assert "--ar 1:1" in composed
        assert "--ar 16:9" not in composed


class TestObjectivesAnchorSubjectAndDemandVariety:
    """Two failures these wordings exist to prevent: a run that swapped the
    operator's subject for an unrelated one (blacksmith tongs in, soap out), and
    a batch of near-identical frames Adobe refuses as similar content."""

    def test_generate_stays_inside_the_message_and_varies_within_it(self):
        objective = prompts._objective("generate", False, count=5)
        assert "THIS message" in objective
        assert "never swap it for an unrelated topic" in objective
        assert "genuinely different" in objective
        # The subject is anchored, so "vary the subject" is no longer a licence
        # to replace it — only the depiction changes.
        assert "that object appears in every prompt" in objective

    def test_batch_explores_different_subjects_inside_the_niche(self):
        objective = prompts._objective("batch", False)
        assert "different subject or variant the niche contains" in objective
        assert "never the same subject reworded" in objective
        assert "do not drift to unrelated" in objective

    def test_both_objectives_still_reference_the_answer_format(self):
        assert "ANSWER FORMAT" in prompts._objective("generate", False)
        assert "ANSWER FORMAT" in prompts._objective("batch", False)


class TestModesOnTheWire:
    def test_generate_creates_a_run(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs",
            json={"message": "a quiet library", "mode": "generate", "count": 3},
        ).json()
        assert payload["mode"] == "generate"
        assert payload["settings"]["count"] == 3

    def test_legacy_static_still_creates_a_run(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert payload["mode"] == "static"


class TestPromptLibrarySearch:
    def _make(self, client, body: str, title: str = "") -> str:
        return client.post(
            "/api/prompts", json={"title": title, "body": body}
        ).json()["id"]

    def test_query_matches_body_case_insensitively(self, client):
        self._make(client, "A misty pine forest at dawn", title="Forest")
        self._make(client, "Neon city street in rain", title="City")
        payload = client.get("/api/prompts", params={"q": "PINE"}).json()
        assert len(payload["items"]) == 1
        assert "pine" in payload["items"][0]["body"].lower()

    def test_query_matches_tags(self, client):
        prompt_id = self._make(client, "body text", title="T")
        client.patch(f"/api/prompts/{prompt_id}", json={"tags": ["warehouse"]})
        payload = client.get("/api/prompts", params={"q": "warehouse"}).json()
        assert [item["id"] for item in payload["items"]] == [prompt_id]

    def test_empty_query_returns_everything(self, client):
        self._make(client, "one")
        self._make(client, "two")
        payload = client.get("/api/prompts", params={"q": ""}).json()
        assert len(payload["items"]) == 2

    def test_search_composes_with_the_status_filter(self, client):
        used = self._make(client, "pinecone study")
        self._make(client, "pine tar recipe")
        client.patch(f"/api/prompts/{used}", json={"status": "USED"})
        payload = client.get(
            "/api/prompts", params={"status": "used", "q": "pine"}
        ).json()
        assert [item["id"] for item in payload["items"]] == [used]

    def test_matches_query_is_pure_and_false_on_miss(self):
        class P:
            title = "Title"
            body = "Body text"
            negative_prompt = None
            tags = ["tag"]

        assert prompt_library.matches_query(P(), "") is True
        assert prompt_library.matches_query(P(), "body") is True
        assert prompt_library.matches_query(P(), "TAG") is True
        assert prompt_library.matches_query(P(), "missing") is False
