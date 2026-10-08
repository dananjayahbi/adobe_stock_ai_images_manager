"""API tests for the Prompt Research router.

The agent itself is covered by ``test_research_agent.py``; these tests are about
the HTTP surface and the *persistence* contract:

* a conversation survives a restart, because the feature's whole point is that
  the operator returns to a research thread;
* the streaming endpoint writes to the **test** database, not the real one;
* an accepted prompt becomes a real Prompt Library prompt, and deleting the
  thread does not delete it.

The agent is stubbed at the router's own seam (``agent.run``), so no test here
needs a model or the network.
"""

from __future__ import annotations

import json

import pytest

from services.research import agent as agent_module
from services.research import events as event_module


@pytest.fixture(autouse=True)
def stream_session_factory(db_session_factory):
    """Point the streaming endpoint at the test database.

    The streamed body outlives the request's dependencies and so opens its own
    session. Without this override it would open a session against the real
    ``storage/adobe_stock.db``: the run would be written to the operator's live
    database, and the test that created it would see a 404 because the
    conversation is not in the test database.
    """
    from main import app
    from routers import research as research_router
    from services.research import inflight

    app.dependency_overrides[research_router.get_session_factory] = (
        lambda: db_session_factory
    )
    # The in-flight registry is process-global, so a leaked claim from one test
    # would make the next test's stream refuse to start.
    inflight.clear()
    yield
    inflight.clear()
    app.dependency_overrides.pop(research_router.get_session_factory, None)


@pytest.fixture()
def stub_agent(monkeypatch):
    """Replace the agent with a scripted event sequence.

    ``collect_events`` in the router drives ``agent.run``, so patching there
    exercises the real request handling, persistence and SSE framing while
    keeping the test deterministic.
    """

    def _install(events=None, answer="Here is my answer."):
        scripted = events if events is not None else [
            event_module.event(event_module.RUN_STARTED, mode="static"),
            event_module.event(event_module.THINKING, text="Thinking about it."),
            event_module.event(event_module.MESSAGE, text=answer),
            event_module.event(
                event_module.PROMPTS,
                prompts=[
                    {
                        "body": "A commercial stock photograph of a factory floor. --ar 16:9",
                        "index": 1,
                        "warnings": [],
                        "duplicate_of": None,
                        "duplicate": False,
                        "chars": 62,
                    }
                ],
                duplicate_pairs=[],
                saveable=["A commercial stock photograph of a factory floor. --ar 16:9"],
            ),
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


class TestResearchSettings:
    def test_settings_expose_modes_and_the_default_style(self, client):
        response = client.get("/api/research/settings")
        assert response.status_code == 200
        payload = response.json()

        mode_ids = {mode["id"] for mode in payload["modes"]}
        assert mode_ids == {"static", "batch", "research", "ideas"}

        # The operator's own reference prompt is the default style.
        assert payload["default_style_instruction"].startswith(
            "Epic commercial stock photograph"
        )
        assert payload["default_style_instruction"].endswith("--ar 16:9")

    def test_only_the_research_modes_offer_the_validity_check(self, client):
        """A scorecard must not be possible in a run that was not asked for one."""
        modes = {mode["id"]: mode for mode in client.get("/api/research/settings").json()["modes"]}
        assert modes["research"]["supports_validity"] is True
        assert modes["ideas"]["supports_validity"] is True
        assert modes["static"]["supports_validity"] is False
        assert modes["batch"]["supports_validity"] is False

    def test_the_ideas_mode_declares_it_produces_no_prompts(self, client):
        modes = {mode["id"]: mode for mode in client.get("/api/research/settings").json()["modes"]}
        assert modes["ideas"]["produces_prompts"] is False
        assert modes["static"]["produces_prompts"] is True

    def test_the_disclaimer_is_served_so_it_cannot_be_dropped(self, client):
        payload = client.get("/api/research/settings").json()
        assert "not a measurement" in payload["disclaimer"]

    def test_the_target_average_is_served(self, client):
        """Served so the card's verdict and the agent's instruction quote the same
        number rather than two copies that can drift."""
        from services.research import validity

        payload = client.get("/api/research/settings").json()
        assert payload["target_average"] == validity.TARGET_AVERAGE


class TestPrioritySources:
    """The upload/download surface for the operator's own source list.

    The file *is* the interface the operator edits, so the server is the only thing
    that decides validity — a client-side parse would turn a format error into a
    silent no-op.
    """

    def test_nothing_uploaded_reports_an_empty_list(self, client):
        payload = client.get("/api/research/sources").json()
        assert payload["sources"] == []
        assert payload["filename"] == ""

    def test_the_template_downloads_as_a_file(self, client):
        response = client.get("/api/research/sources/template")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]
        assert "research-priority-sources.json" in response.headers["content-disposition"]

    def test_the_template_is_valid_json_that_the_uploader_accepts(self, client):
        """The point of a downloadable template is that it can be uploaded back
        unchanged — that is what makes it a specification rather than a sketch."""
        template = client.get("/api/research/sources/template").text
        response = client.post(
            "/api/research/sources",
            json={"content": template, "filename": "template.json"},
        )
        assert response.status_code == 200, response.text
        assert len(response.json()["sources"]) >= 3

    def test_an_uploaded_file_is_stored_and_read_back(self, client):
        body = {
            "version": 1,
            "sources": [
                {"url": "https://stock.adobe.com/search", "name": "Adobe Stock"},
                {"url": "https://www.shutterstock.com/search", "priority": 2},
            ],
        }
        response = client.post(
            "/api/research/sources",
            json={"content": json.dumps(body), "filename": "mine.json"},
        )
        assert response.status_code == 200
        assert response.json()["filename"] == "mine.json"

        stored = client.get("/api/research/sources").json()
        assert len(stored["sources"]) == 2
        assert stored["sources"][0]["name"] == "Adobe Stock"
        assert stored["filename"] == "mine.json"

    def test_a_bad_file_is_refused_with_the_reason(self, client):
        """A file that uploads and silently does nothing is indistinguishable from
        the feature being broken."""
        response = client.post(
            "/api/research/sources",
            json={"content": "this is not json", "filename": "bad.json"},
        )
        assert response.status_code == 400
        assert "JSON" in response.json()["detail"]

    def test_a_refused_upload_leaves_the_previous_list_working(self, client):
        """Validated before anything is written, so a mistake cannot wipe a list the
        operator spent time on."""
        good = {"sources": [{"url": "https://stock.adobe.com/search"}]}
        client.post("/api/research/sources", json={"content": json.dumps(good)})
        client.post("/api/research/sources", json={"content": "{ broken"})
        assert len(client.get("/api/research/sources").json()["sources"]) == 1

    def test_a_non_url_entry_is_refused(self, client):
        response = client.post(
            "/api/research/sources",
            json={"content": json.dumps(["javascript:alert(1)"])},
        )
        assert response.status_code == 400

    def test_deleting_removes_the_list(self, client):
        body = {"sources": [{"url": "https://stock.adobe.com/search"}]}
        client.post("/api/research/sources", json={"content": json.dumps(body)})
        response = client.delete("/api/research/sources")
        assert response.status_code == 200
        assert response.json()["sources"] == []
        assert client.get("/api/research/sources").json()["sources"] == []

    def test_a_stored_file_reaches_the_run_request(self, client, monkeypatch):
        """The end-to-end claim: an uploaded file changes what the agent is sent."""
        from services.research import source_store

        body = {
            "sources": [
                {"url": "https://stock.adobe.com/search", "name": "Adobe Stock search"}
            ]
        }
        client.post("/api/research/sources", json={"content": json.dumps(body)})

        captured: list = []

        def _run(request):  # noqa: ANN001
            captured.append(request)
            yield event_module.event(event_module.RUN_FINISHED, status="completed")

        monkeypatch.setattr(agent_module, "run", _run)
        client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "static", "stream_first": False},
        )
        assert captured, "the agent was never run"
        assert captured[0].priority_sources is not None
        assert captured[0].priority_sources.sources[0].name == "Adobe Stock search"
        # And it is cleared again so later tests are not affected.
        source_store.clear()

    def test_no_file_means_no_priority_sources_on_the_request(self, client, monkeypatch):
        """A run without a file must behave exactly as it did before the feature."""
        captured: list = []

        def _run(request):  # noqa: ANN001
            captured.append(request)
            yield event_module.event(event_module.RUN_FINISHED, status="completed")

        monkeypatch.setattr(agent_module, "run", _run)
        client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "static", "stream_first": False},
        )
        assert captured[0].priority_sources is None


class TestCreateRun:
    def test_a_run_is_created_and_its_answer_stored(self, client, stub_agent):
        stub_agent()
        response = client.post(
            "/api/research/runs",
            json={"message": "automated warehouses", "mode": "static", "count": 2},
        )
        assert response.status_code == 201
        payload = response.json()

        assert payload["mode"] == "static"
        assert payload["status"] == "COMPLETED"
        assert payload["title"] == "automated warehouses"
        assert payload["result"]["prompts"]
        # Both the user turn and the assistant answer are in the conversation.
        roles = [turn["role"] for turn in payload["messages"]]
        assert roles == ["user", "assistant"]
        assert payload["messages"][1]["content"] == "Here is my answer."

    def test_the_transcript_is_stored_for_replay(self, client, stub_agent):
        """A reloaded page must replay what happened, not show a bare result."""
        stub_agent()
        payload = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        types = [event["type"] for event in payload["events"]]
        assert event_module.THINKING in types
        assert event_module.PROMPTS in types

    def test_thinking_is_persisted_on_the_result(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert payload["result"]["thinking"] == "Thinking about it."

    def test_the_context_report_is_persisted(self, client, stub_agent):
        """A replayed conversation must show the same indicator the live one did;
        a reloaded thread with an empty bar reads as "no data"."""
        stub_agent(
            events=[
                event_module.event(event_module.RUN_STARTED, mode="static"),
                event_module.event(
                    event_module.CONTEXT,
                    used_tokens=1234,
                    window_tokens=200_000,
                    level="ok",
                    compacted=False,
                ),
                event_module.event(
                    event_module.RUN_FINISHED, status="completed", answer="done"
                ),
            ],
            answer="done",
        )
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        stored = client.get(f"/api/research/runs/{created['id']}").json()
        assert stored["result"]["context"]["used_tokens"] == 1234
        assert stored["result"]["context"]["window_tokens"] == 200_000

    def test_the_settings_expose_the_context_window_and_thresholds(self, client):
        """The bar's thresholds and the backend's folding decision must not drift,
        so both come from the same place."""
        payload = client.get("/api/research/settings").json()
        assert payload["context_window"] > 0
        assert payload["keep_recent_turns"] >= 1
        assert 0 < payload["compact_at_share"] < payload["warn_at_share"] <= 1

    def test_a_folded_history_is_reported_to_the_client(self, client, monkeypatch):
        """The operator has to know the conversation was compacted: a summary that
        silently dropped a finding would make the model reason from a hole."""
        captured: list[agent_module.RunRequest] = []

        def _run(request):  # noqa: ANN001
            captured.append(request)
            yield event_module.event(
                event_module.CONTEXT,
                used_tokens=10,
                window_tokens=20_000,
                compacted=True,
                folded_turns=7,
                level="ok",
            )
            yield event_module.event(
                event_module.RUN_FINISHED, status="completed", answer="done"
            )

        monkeypatch.setattr(agent_module, "run", _run)
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        stored = client.get(f"/api/research/runs/{created['id']}").json()
        assert stored["result"]["context"]["folded_turns"] == 7
        assert stored["result"]["context"]["compacted"] is True
        # The request carried the resolved window, which is what enables folding:
        # a zero window disables it entirely.
        assert captured[0].context_window > 0

    def test_an_invalid_mode_is_rejected(self, client):
        response = client.post(
            "/api/research/runs", json={"message": "x", "mode": "nonsense"}
        )
        assert response.status_code == 400
        assert "static" in response.json()["detail"]

    def test_an_empty_message_is_rejected(self, client):
        response = client.post(
            "/api/research/runs", json={"message": "   ", "mode": "static"}
        )
        assert response.status_code == 400

    def test_the_prompt_count_is_clamped(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "batch", "count": 9999},
        ).json()
        assert payload["settings"]["count"] <= 60

    def test_a_mode_that_produces_no_prompts_is_given_no_count(self, client, stub_agent):
        """Telling an ideas run to produce N prompts would ask it to answer a
        question the operator did not ask."""
        stub_agent()
        payload = client.post(
            "/api/research/runs",
            json={"message": "what is worth shooting?", "mode": "ideas", "count": 5},
        ).json()
        assert payload["settings"]["count"] == 0

    def test_validity_is_refused_in_a_mode_that_does_not_support_it(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "static", "validity_check": True},
        ).json()
        assert payload["settings"]["validity_check"] is False

    def test_the_default_style_is_recorded_when_none_is_given(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert payload["settings"]["style_instruction"].startswith(
            "Epic commercial stock photograph"
        )

    def test_a_custom_style_instruction_is_recorded(self, client, stub_agent):
        stub_agent()
        payload = client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "static", "style_instruction": "MY STYLE"},
        ).json()
        assert payload["settings"]["style_instruction"] == "MY STYLE"

    def test_a_failing_run_is_stored_as_failed_with_its_error(self, client, stub_agent):
        """A failure must be visible in the thread, not an empty conversation."""
        stub_agent(
            events=[
                event_module.event(event_module.RUN_STARTED, mode="static"),
                event_module.event(event_module.ERROR, text="HTTP 401: bad key"),
                event_module.event(event_module.RUN_FINISHED, status="error", answer=""),
            ],
            answer="",
        )
        payload = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert payload["status"] == "FAILED"
        assert "401" in payload["error"]


class TestDeferredFirstTurn:
    """Creating a conversation without running its opening turn.

    The research page uses this so the *first* turn streams: a buffered first turn
    would leave the live view blank for the whole minute the agent works, which is
    the opposite of the feature.
    """

    def test_stream_first_creates_a_run_without_running_it(self, client, stub_agent):
        stub_agent()
        response = client.post(
            "/api/research/runs",
            json={"message": "automated warehouses", "mode": "research", "stream_first": True},
        )
        assert response.status_code == 201
        payload = response.json()
        # The conversation exists, with the question stored, but nothing has run.
        assert payload["status"] == "RUNNING"
        assert payload["messages"] == [
            {"role": "user", "content": "automated warehouses", "created_at": payload["messages"][0]["created_at"]}
        ]
        assert payload["result"] == {}

    def test_the_deferred_turn_streams_and_does_not_duplicate_the_question(
        self, client, stub_agent
    ):
        """The opening message was stored at creation; the stream must not
        append it again, or the operator's question appears twice."""
        stub_agent()
        created = client.post(
            "/api/research/runs",
            json={"message": "automated warehouses", "mode": "research", "stream_first": True},
        ).json()

        with client.stream(
            "GET", f"/api/research/runs/{created['id']}/stream"
        ) as response:
            assert response.status_code == 200
            "".join(response.iter_text())

        fetched = client.get(f"/api/research/runs/{created['id']}").json()
        assert fetched["status"] == "COMPLETED"
        user_turns = [
            turn["content"] for turn in fetched["messages"] if turn["role"] == "user"
        ]
        assert user_turns == ["automated warehouses"]

    def test_a_stream_with_no_message_and_no_stored_turn_is_rejected(
        self, client, stub_agent
    ):
        """There is nothing to answer, so the run must not start."""
        stub_agent()
        created = client.post(
            "/api/research/runs",
            json={"message": "x", "mode": "static", "stream_first": True},
        ).json()

        # Remove the stored turn, simulating an empty conversation.
        from database import get_db
        from main import app
        from services.research import runs as runs_module

        override = app.dependency_overrides[get_db]
        session = next(override())
        run = runs_module.get_run(session, created["id"])
        run.messages = []
        session.commit()
        session.close()

        response = client.get(f"/api/research/runs/{created['id']}/stream")
        assert response.status_code == 400
        assert "message is required" in response.json()["detail"].lower()


class TestConversations:
    def test_runs_are_listed_newest_first(self, client, stub_agent):
        stub_agent()
        for message in ("first", "second", "third"):
            client.post("/api/research/runs", json={"message": message, "mode": "static"})

        payload = client.get("/api/research/runs").json()
        assert payload["total"] == 3
        assert payload["items"][0]["title"] == "third"

    def test_the_list_reports_the_prompt_count_and_whether_validity_ran(
        self, client, stub_agent
    ):
        stub_agent()
        client.post("/api/research/runs", json={"message": "x", "mode": "static"})
        item = client.get("/api/research/runs").json()["items"][0]
        assert item["prompt_count"] == 1
        assert item["has_validity"] is False

    def test_a_conversation_is_readable_with_its_transcript(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        fetched = client.get(f"/api/research/runs/{created['id']}").json()
        assert fetched["id"] == created["id"]
        assert fetched["events"]
        assert fetched["messages"][0]["content"] == "x"

    def test_a_missing_conversation_is_a_404(self, client):
        assert client.get("/api/research/runs/nope").status_code == 404

    def test_a_follow_up_turn_is_appended_and_the_history_is_carried(
        self, client, stub_agent, monkeypatch
    ):
        """The operator says "continue with this idea"; the agent must know which."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "automated warehouses", "mode": "research"}
        ).json()

        seen: dict = {}
        original = agent_module.run

        def _capture(request):  # noqa: ANN001
            seen["request"] = request
            yield from original(request)

        monkeypatch.setattr(agent_module, "run", _capture)

        client.post(
            f"/api/research/runs/{created['id']}/messages",
            json={"message": "continue with this idea"},
        )

        history = seen["request"].history
        contents = [turn["content"] for turn in history]
        assert "automated warehouses" in contents
        assert "Here is my answer." in contents

    def test_a_follow_up_keeps_the_style_and_validity_settings(
        self, client, stub_agent, monkeypatch
    ):
        stub_agent()
        created = client.post(
            "/api/research/runs",
            json={
                "message": "x",
                "mode": "research",
                "validity_check": True,
                "style_instruction": "KEEP ME",
            },
        ).json()

        seen: dict = {}
        original = agent_module.run

        def _capture(request):  # noqa: ANN001
            seen["request"] = request
            yield from original(request)

        monkeypatch.setattr(agent_module, "run", _capture)
        client.post(
            f"/api/research/runs/{created['id']}/messages", json={"message": "continue"}
        )

        assert seen["request"].style_instruction == "KEEP ME"
        assert seen["request"].validity_check is True

    def test_an_opening_run_uses_the_saved_house_rules(
        self, client, stub_agent, monkeypatch
    ):
        """End to end: the rules the operator edited must reach the model.

        Without this the house-rules editor would be a fully working save that
        changes nothing about what the agent is told — the editor would report
        success while the run silently used the shipped constant.
        """
        stub_agent()
        client.put(
            "/api/research/style", json={"house_rules": "- THE RUN MUST SEE THIS."}
        )

        seen: dict = {}
        original = agent_module.run

        def _capture(request):  # noqa: ANN001
            seen["request"] = request
            yield from original(request)

        monkeypatch.setattr(agent_module, "run", _capture)
        client.post("/api/research/runs", json={"message": "x", "mode": "static"})

        assert "- THE RUN MUST SEE THIS." in seen["request"].house_rules

    def test_a_follow_up_turn_picks_up_a_house_rules_edit(
        self, client, stub_agent, monkeypatch
    ):
        """The rules are the operator's *current* standard, not a run snapshot.

        The opposite of the style instruction, which is snapshotted onto the
        run: an open conversation should adopt a rules edit made while it sits on
        screen, or the editor looks broken for the whole thread's life.
        """
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        client.put(
            "/api/research/style", json={"house_rules": "- EDITED MID THREAD."}
        )

        seen: dict = {}
        original = agent_module.run

        def _capture(request):  # noqa: ANN001
            seen["request"] = request
            yield from original(request)

        monkeypatch.setattr(agent_module, "run", _capture)
        client.post(
            f"/api/research/runs/{created['id']}/messages", json={"message": "again"}
        )

        assert "- EDITED MID THREAD." in seen["request"].house_rules

    def test_an_empty_follow_up_is_rejected(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        response = client.post(
            f"/api/research/runs/{created['id']}/messages", json={"message": "  "}
        )
        assert response.status_code == 400


class TestStreaming:
    def test_the_stream_emits_sse_frames_and_a_done_marker(self, client, stub_agent):
        """The live view is the feature; a buffered response would defeat it."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        with client.stream(
            "GET",
            f"/api/research/runs/{created['id']}/stream",
            params={"message": "more please"},
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            body = "".join(response.iter_text())

        assert "data: " in body
        assert "event: done" in body
        # Each data line must be a complete JSON object. The `done` frame's body
        # is `{}` (it is a stream marker, not a run event), so it is filtered out
        # before asserting on the run's own events.
        payloads = [
            json.loads(line[len("data: ") :])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        run_events = [payload for payload in payloads if "type" in payload]
        assert any(payload["type"] == event_module.THINKING for payload in run_events)
        assert run_events[-1]["type"] == event_module.RUN_FINISHED

    def test_the_stream_persists_the_turn(self, client, stub_agent):
        """A client that disconnects must still leave a usable thread, not one
        stuck at RUNNING forever."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        with client.stream(
            "GET",
            f"/api/research/runs/{created['id']}/stream",
            params={"message": "another question"},
        ) as response:
            "".join(response.iter_text())

        fetched = client.get(f"/api/research/runs/{created['id']}").json()
        assert fetched["status"] == "COMPLETED"
        contents = [turn["content"] for turn in fetched["messages"]]
        assert "another question" in contents
        assert fetched["messages"][-1]["content"] == "Here is my answer."

    def test_the_stream_refuses_a_conversation_that_is_already_running(
        self, client, stub_agent
    ):
        """Two concurrent turns on one thread would interleave the transcript.

        The guard is the *in-flight* registry, not the stored status. Using the
        status was a real deadlock: a conversation is created RUNNING because it
        is awaiting its first turn, so the guard refused the turn meant to start
        it. And a run left RUNNING by a crash would have blocked every future turn
        on that thread forever.
        """
        from services.research import inflight

        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        # Claim the conversation as if a turn were executing right now.
        assert inflight.begin(created["id"]) is True
        try:
            response = client.get(
                f"/api/research/runs/{created['id']}/stream", params={"message": "again"}
            )
            assert response.status_code == 409
        finally:
            inflight.end(created["id"])

    def test_a_stored_running_status_does_not_block_a_new_turn(self, client, stub_agent):
        """A crashed process must not lock a conversation forever."""
        from database import get_db
        from main import app
        from models import ResearchRunStatus
        from services.research import runs as runs_module

        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        override = app.dependency_overrides[get_db]
        session = next(override())
        run = runs_module.get_run(session, created["id"])
        run.status = ResearchRunStatus.RUNNING
        session.commit()
        session.close()

        # No turn is executing in this process, so the stream must proceed.
        with client.stream(
            "GET", f"/api/research/runs/{created['id']}/stream", params={"message": "go"}
        ) as response:
            assert response.status_code == 200
            "".join(response.iter_text())

    def test_the_in_flight_claim_is_released_when_the_stream_ends(
        self, client, stub_agent
    ):
        """A claim left behind would make every later turn on the thread fail."""
        from services.research import inflight

        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        with client.stream(
            "GET", f"/api/research/runs/{created['id']}/stream", params={"message": "one"}
        ) as response:
            "".join(response.iter_text())

        assert inflight.is_running(created["id"]) is False

    def test_a_missing_conversation_stream_is_a_404(self, client):
        response = client.get("/api/research/runs/nope/stream", params={"message": "x"})
        assert response.status_code == 404

    def test_an_empty_streamed_message_is_rejected(self, client, stub_agent):
        """A whitespace-only message passes the query's min_length, so the app's
        own validation is what rejects it — with a message, not a bare 422."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        response = client.get(
            f"/api/research/runs/{created['id']}/stream", params={"message": "   "}
        )
        assert response.status_code == 400
        assert "message is required" in response.json()["detail"].lower()


class TestTranscriptStorage:
    def test_streamed_text_fragments_are_coalesced(self):
        """A streaming run emits one event per token fragment.

        Measured live: a single 48-second turn produced 600 events — exactly the
        storage cap, so the transcript was trimmed from the front and a reloaded
        page started mid-run. Coalescing preserves the text and ordering while
        cutting the count by ~2 orders of magnitude.
        """
        from services.research import events as ev
        from services.research.runs import coalesce_events

        fragments = [ev.event(ev.THINKING, text=f"t{index}") for index in range(50)]
        fragments += [ev.event(ev.MESSAGE, text=f"m{index}") for index in range(50)]
        merged = coalesce_events(fragments)

        assert len(merged) == 2
        assert merged[0]["text"] == "".join(f"t{index}" for index in range(50))
        assert merged[1]["text"] == "".join(f"m{index}" for index in range(50))

    def test_coalescing_does_not_merge_across_other_events(self):
        """Every non-text event is a discrete fact whose position matters."""
        from services.research import events as ev
        from services.research.runs import coalesce_events

        payloads = [
            ev.event(ev.THINKING, text="a"),
            ev.event(ev.TOOL_CALL, name="web_search", arguments={}, summary="s"),
            ev.event(ev.THINKING, text="b"),
            ev.event(ev.SOURCES, sources=[{"url": "https://x.com"}]),
            ev.event(ev.THINKING, text="c"),
        ]
        merged = coalesce_events(payloads)
        assert [entry["type"] for entry in merged] == [
            ev.THINKING,
            ev.TOOL_CALL,
            ev.THINKING,
            ev.SOURCES,
            ev.THINKING,
        ]
        assert [entry.get("text") for entry in merged if entry["type"] == ev.THINKING] == [
            "a",
            "b",
            "c",
        ]

    def test_a_stored_transcript_is_well_under_the_cap(self, client, stub_agent):
        """The cap must be a safety net, not something a normal run reaches."""
        from services.research import events as ev

        fragments = [ev.event(ev.MESSAGE, text=f"word{index} ") for index in range(300)]
        fragments.append(ev.event(ev.RUN_FINISHED, status="completed", answer="done"))
        stub_agent(events=fragments, answer="done")

        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert len(created["events"]) < 20

    def test_a_run_that_records_a_validity_score_is_persisted(self, client, stub_agent):
        """The flagship path, and the one that was silently broken.

        ``result`` is a JSON column, and ``_finish`` was storing the ``ValidityView``
        dataclass that ``validity.describe`` returns. That raises
        ``TypeError: Object of type ValidityView is not JSON serializable`` — and
        because it happens inside the stream's ``finally`` block, the turn is lost
        and the conversation stays RUNNING forever. Only the *success* path of the
        validity gate hit it: a run with no assessment stores ``None``, which
        serialises fine, so every earlier test passed.
        """
        from services.research import events as ev

        assessment = {
            "customer_download_confidence": 62.0,
            "adobe_acceptance_confidence": 74.0,
            "collective_average": 68.0,
            "reasoning": "Moderate supply, clear demand signal.",
            "evidence": ["4 marketplaces carry this niche"],
        }
        stub_agent(
            events=[
                ev.event(ev.RUN_STARTED, mode="research"),
                ev.event(ev.TOOL_CALL, name="assess_validity", arguments={}, summary="s"),
                ev.event(ev.VALIDITY, validity=assessment, follow_up_actions=[]),
                ev.event(ev.RUN_FINISHED, status="completed", answer="Verdict: moderate."),
            ],
            answer="Verdict: moderate.",
        )

        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "research"}
        ).json()
        stored = client.get(f"/api/research/runs/{created['id']}").json()

        assert stored["status"] == "COMPLETED"
        assert stored["error"] in (None, "")
        # The scorecard is stored as plain data, not a dataclass.
        assert stored["result"]["validity"]["collective_average"] == 68.0
        assert stored["result"]["validity"]["collective_label"]
        assert stored["result"]["validity"]["disclaimer"]
        # And it survives a JSON round trip, which is what the column does.
        assert isinstance(stored["result"]["validity"], dict)
        # The summary the thread list reads is populated too.
        listed = client.get("/api/research/runs?limit=5").json()["items"]
        entry = next(item for item in listed if item["id"] == created["id"])
        assert entry["has_validity"] is True

    def test_a_failed_persistence_marks_the_run_failed(self, client, stub_agent, monkeypatch):
        """A run left at RUNNING reports a turn that has ended. Recording the
        failure turns an invisible loss into a thread the operator can retry."""
        from routers import research as research_router

        stub_agent()

        def exploding_finish(db, run, accumulated, emitted):  # noqa: ANN001
            raise TypeError("Object of type ValidityView is not JSON serializable")

        monkeypatch.setattr(research_router, "_finish", exploding_finish)

        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        stored = client.get(f"/api/research/runs/{created['id']}").json()

        assert stored["status"] == "FAILED"
        assert "could not be saved" in (stored["error"] or "")


class TestAcceptingPrompts:
    def test_accepted_prompts_become_library_prompts(self, client, stub_agent):
        """The bridge between research and production."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        response = client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Prompt alpha. --ar 16:9", "Prompt beta. --ar 16:9"]},
        )
        assert response.status_code == 200
        assert response.json()["count"] == 2

        library = client.get("/api/prompts").json()
        bodies = {item["body"] for item in library["items"]}
        assert "Prompt alpha. --ar 16:9" in bodies
        assert "Prompt beta. --ar 16:9" in bodies

    def test_accepted_prompts_start_as_drafts(self, client, stub_agent):
        """A new prompt has produced nothing yet, so it is not 'used'."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["A fresh prompt. --ar 16:9"]},
        )
        library = client.get("/api/prompts").json()
        stored = next(item for item in library["items"] if item["body"].startswith("A fresh"))
        assert stored["status"] == "DRAFT"

    def test_accepting_the_same_prompt_twice_does_not_duplicate_it(
        self, client, stub_agent
    ):
        """A double click must not create two identical library entries."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()

        first = client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Only once. --ar 16:9"]},
        ).json()
        second = client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Only once. --ar 16:9"]},
        ).json()

        assert first["count"] == 1
        assert second["count"] == 0
        assert second["skipped"] == ["Only once. --ar 16:9"]

    def test_accepting_records_which_prompts_were_kept(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Tracked. --ar 16:9"]},
        )
        fetched = client.get(f"/api/research/runs/{created['id']}").json()
        assert fetched["result"]["accepted_prompt_ids"]

    def test_an_empty_accept_list_is_rejected(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        response = client.post(
            f"/api/research/runs/{created['id']}/accept", json={"prompts": []}
        )
        assert response.status_code == 400

    def test_tags_and_a_negative_prompt_can_be_attached(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={
                "prompts": ["Tagged prompt. --ar 16:9"],
                "tags": ["logistics", "warehouse"],
                "negative_prompt": "text, watermark",
            },
        )
        library = client.get("/api/prompts").json()
        stored = next(item for item in library["items"] if item["body"].startswith("Tagged"))
        assert stored["tags"] == ["logistics", "warehouse"]
        assert stored["negative_prompt"] == "text, watermark"

    def test_per_prompt_metadata_reaches_the_library(self, client, stub_agent):
        """The point of the JSON contract: the model's own title, tags and
        category survive the last step instead of being discarded."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={
                "prompts": ["A vast automated parcel hall. --ar 16:9"],
                "tags": ["logistics"],
                "details": [
                    {
                        "title": "Parcel hall at dawn",
                        "tags": ["automation", "robotics"],
                        "category": 10,
                    }
                ],
            },
        )
        library = client.get("/api/prompts").json()
        stored = next(
            item for item in library["items"] if item["body"].startswith("A vast automated")
        )
        # The model's title wins over the derived one.
        assert stored["title"] == "Parcel hall at dawn"
        # Per-prompt tags are merged with the run-level ones, not replacing them.
        assert set(stored["tags"]) == {"logistics", "automation", "robotics"}
        assert stored["params"]["category"] == 10

    def test_a_missing_title_falls_back_to_a_derived_one(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Derived title case. --ar 16:9"], "details": [{}]},
        )
        library = client.get("/api/prompts").json()
        stored = next(
            item for item in library["items"] if item["body"].startswith("Derived title case")
        )
        assert stored["title"]

    def test_details_shorter_than_the_prompt_list_is_tolerated(self, client, stub_agent):
        """A malformed request must not crash the endpoint — the body is what the
        library actually needs."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        response = client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={
                "prompts": ["One. --ar 16:9", "Two. --ar 16:9"],
                "details": [{"title": "Only the first"}],
            },
        )
        assert response.status_code == 200
        assert response.json()["count"] == 2


class TestDeleting:
    def test_deleting_a_conversation_removes_it(self, client, stub_agent):
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        assert client.delete(f"/api/research/runs/{created['id']}").status_code == 200
        assert client.get(f"/api/research/runs/{created['id']}").status_code == 404

    def test_deleting_a_conversation_keeps_the_prompts_it_produced(
        self, client, stub_agent
    ):
        """Prompts already accepted are production work; deleting a research
        thread must not delete them."""
        stub_agent()
        created = client.post(
            "/api/research/runs", json={"message": "x", "mode": "static"}
        ).json()
        client.post(
            f"/api/research/runs/{created['id']}/accept",
            json={"prompts": ["Keep me. --ar 16:9"]},
        )

        client.delete(f"/api/research/runs/{created['id']}")

        library = client.get("/api/prompts").json()
        assert any(item["body"] == "Keep me. --ar 16:9" for item in library["items"])
