"""Tool-call argument validation, and the prompt-mode answer guarantee.

Two defects the operator reported, and the tests that pin their fixes:

1. **"The agent couldn't call the relevant tools properly."** A call with a
   missing or empty required argument used to *run*, spend a budget slot, and
   return a result that said nothing about the subject. It is now rejected before
   it runs, with a correction naming the argument and showing the exact shape.
2. **"Sometimes the agent suddenly stops without providing the prompts."** A
   prompt-mode run whose reply is not the JSON contract used to finish as a
   *success* with zero prompts. It is now asked to resend, and only then accepted.
"""

from __future__ import annotations

import json

import pytest

from services.research import (
    agent,
    events as event_module,
    prompts,
    protocol,
    synthesis,
    toolcall,
    tools,
)

HOUSE_PROMPT = (
    "Epic commercial stock photograph of a vast automated greenhouse with "
    "robotic arms tending leafy crops under diffuse volumetric daylight, "
    "wide-angle 20mm lens, f/6.3, deep cinematic focus across the 16:9 frame, "
    "clean editorial copy space in the upper third, unmanned, pristine surfaces, "
    "zero text, zero brand logos, ready for high-resolution upscaling. --ar 16:9"
)


def scripted_stream(script: list[list[tuple[str, str]]]):
    """A ``stream_chat`` replacement that replays a fixed turn sequence."""
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


def json_answer(count: int = 1) -> str:
    """A compliant JSON-contract answer."""
    return json.dumps(
        {
            "summary": "Produced prompts.",
            "prompts": [
                {
                    "title": f"Prompt {index + 1}",
                    "body": f"{HOUSE_PROMPT} Variation {index + 1}.",
                    "category": 10,
                }
                for index in range(count)
            ],
        }
    )


@pytest.fixture()
def stub_search(monkeypatch):
    """Replace the network search with a deterministic result set."""
    from services.research import search as search_module

    def _install(count: int = 3):
        response = search_module.SearchResponse(
            query="q",
            results=[
                search_module.SearchResult(
                    title=f"Result {index}",
                    url="https://www.shutterstock.com/search/x",
                    snippet=f"Snippet {index}",
                )
                for index in range(count)
            ],
            ok=True,
        )
        monkeypatch.setattr(search_module, "search", lambda *a, **k: response)
        return response

    return _install


# --------------------------------------------------------------------------- #
# Argument validation
# --------------------------------------------------------------------------- #

SEARCH_PARAMETERS = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "Search terms."}},
    "required": ["query"],
}


class TestArgumentValidation:
    def test_a_complete_call_is_accepted(self):
        verdict = toolcall.validate_arguments(
            "web_search", {"query": "logistics"}, SEARCH_PARAMETERS
        )
        assert verdict.ok is True
        assert verdict.missing == ()

    def test_a_missing_required_argument_is_rejected(self):
        """Measured live: a call with an empty `niche` ran and answered
        'No niche given', and the turn was spent."""
        verdict = toolcall.validate_arguments("web_search", {}, SEARCH_PARAMETERS)
        assert verdict.ok is False
        assert verdict.missing == ("query",)

    def test_an_empty_string_is_rejected_like_a_missing_one(self):
        """`{"niche": ""}` is the failure that matters: the model believed the
        call was complete, so the tool would run on nothing."""
        verdict = toolcall.validate_arguments(
            "web_search", {"query": "   "}, SEARCH_PARAMETERS
        )
        assert verdict.ok is False
        assert "query" in verdict.missing

    def test_a_null_argument_is_rejected(self):
        verdict = toolcall.validate_arguments(
            "web_search", {"query": None}, SEARCH_PARAMETERS
        )
        assert verdict.ok is False

    def test_an_empty_list_argument_is_rejected(self):
        parameters = {
            "properties": {"prompts": {"type": "array"}},
            "required": ["prompts"],
        }
        assert toolcall.validate_arguments("t", {"prompts": []}, parameters).ok is False
        assert (
            toolcall.validate_arguments("t", {"prompts": ["a"]}, parameters).ok is True
        )

    def test_a_tool_with_no_required_arguments_is_never_blocked(self):
        parameters = {"properties": {"note": {"type": "string"}}, "required": []}
        assert toolcall.validate_arguments("t", {}, parameters).ok is True

    def test_a_tool_with_no_schema_is_never_blocked(self):
        assert toolcall.validate_arguments("t", {}, None).ok is True
        assert toolcall.validate_arguments("t", {}, {}).ok is True

    def test_the_correction_names_the_missing_argument(self):
        verdict = toolcall.validate_arguments("web_search", {}, SEARCH_PARAMETERS)
        assert "`query`" in verdict.text
        assert "CALL REJECTED" in verdict.text

    def test_the_correction_shows_the_exact_shape_to_resend(self):
        """A model reproduces a shape it can copy far more reliably than one it
        has to assemble."""
        verdict = toolcall.validate_arguments("web_search", {}, SEARCH_PARAMETERS)
        assert "<tool_call>" in verdict.text
        assert '"name": "web_search"' in verdict.text
        assert '"query"' in verdict.text

    def test_the_correction_says_it_is_not_evidence(self):
        """Otherwise the model reads "nothing" as a finding about the subject."""
        verdict = toolcall.validate_arguments("web_search", {}, SEARCH_PARAMETERS)
        assert "not treat this" in verdict.text.lower()
        assert "evidence" in verdict.text.lower()

    def test_the_correction_says_it_did_not_cost_a_slot(self):
        verdict = toolcall.validate_arguments("web_search", {}, SEARCH_PARAMETERS)
        assert "budget" in verdict.text.lower()

    def test_the_example_uses_plausible_values_not_the_word_value(self):
        example = toolcall.example_arguments(SEARCH_PARAMETERS)
        assert example["query"] != "value"
        assert example["query"]

    def test_example_types_match_the_declared_schema(self):
        parameters = {
            "properties": {
                "queries": {"type": "array"},
                "count": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["queries", "count", "text"],
        }
        example = toolcall.example_arguments(parameters)
        assert isinstance(example["queries"], list)
        assert isinstance(example["count"], int)
        assert isinstance(example["text"], str)

    def test_a_real_tool_registry_declares_its_requirements(self):
        """The validation is driven by the registry, so the registry has to carry
        the information — otherwise nothing is ever checked."""
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        search = registry["web_search"]
        assert toolcall.required_arguments(search.parameters)
        assert toolcall.validate_arguments("web_search", {}, search.parameters).ok is False

    def test_every_tool_that_requires_an_argument_can_be_validated(self):
        """A tool declaring a required argument that the validator cannot read
        would silently accept a call with nothing in it."""
        registry = tools.registry_for(wants_prompts=True, validity_check=True)
        for name, tool in registry.items():
            required = toolcall.required_arguments(tool.parameters)
            if not required:
                continue
            verdict = toolcall.validate_arguments(name, {}, tool.parameters)
            assert verdict.ok is False, f"{name} accepted an empty call"
            assert verdict.missing == required


# --------------------------------------------------------------------------- #
# The loop: rejection is corrected, not charged
# --------------------------------------------------------------------------- #

class TestRejectedCallInTheLoop:
    def test_an_empty_argument_call_is_not_run_and_not_charged(self, monkeypatch, stub_search):
        """The turn is spent, but the tool-call *slot* is not: charging for a call
        that never ran would let a model burn a whole run on retries."""
        stub_search()
        stream = scripted_stream(
            [
                [("content", '<tool_call>{"name": "web_search", "arguments": {"query": ""}}</tool_call>')],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="static", message="x", max_tool_calls=1)
        )

        results = [p for p in emitted if p["type"] == event_module.TOOL_RESULT]
        assert results[0]["ok"] is False
        assert "Rejected" in results[0]["summary"]
        # The rejection reached the model as an error-marked result.
        second_turn = " ".join(
            str(message.get("content", "")) for message in stream.calls[1]
        )
        assert "CALL REJECTED" in second_turn
        assert 'error="true"' in second_turn

    def test_a_rejected_call_does_not_exhaust_the_budget(self, monkeypatch, stub_search):
        """With one slot and one rejection, the model must still be able to make a
        real call afterwards."""
        stub_search()
        stream = scripted_stream(
            [
                [("content", '<tool_call>{"name": "web_search", "arguments": {}}</tool_call>')],
                [("content", '<tool_call>{"name": "web_search", "arguments": {"query": "logistics"}}</tool_call>')],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(
            agent.RunRequest(mode="static", message="x", max_tool_calls=1)
        )

        calls = [p for p in emitted if p["type"] == event_module.TOOL_CALL]
        results = [p for p in emitted if p["type"] == event_module.TOOL_RESULT]
        assert len(calls) == 2
        # The second call actually ran.
        assert results[1]["ok"] is True
        # And the run did not hit the budget notice.
        assert not any(
            p["type"] == event_module.NOTICE and "call limit" in p.get("text", "")
            for p in emitted
        )


# --------------------------------------------------------------------------- #
# Prompt-mode answer guarantee
# --------------------------------------------------------------------------- #

class TestPromptModeNeverSilentlyReturnsNothing:
    def test_a_prose_answer_in_a_prompt_mode_is_nudged_for_a_resend(self, monkeypatch):
        """The operator's report: the run "suddenly stops without providing the
        prompts". It had completed and delivered nothing."""
        stream = scripted_stream(
            [
                [("content", "I researched the niche thoroughly and here is what I found.")],
                [("content", json_answer(2))],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(mode="static", message="x", count=2)
        )

        assert any(
            p["type"] == event_module.NOTICE and "required format" in p.get("text", "")
            for p in emitted
        )
        prompts_event = next(p for p in emitted if p["type"] == event_module.PROMPTS)
        assert len(prompts_event["prompts"]) == 2
        assert "2 prompts written" in result["message"]

    def test_the_nudge_states_that_nothing_could_be_read(self, monkeypatch):
        stream = scripted_stream(
            [[("content", "Prose answer.")], [("content", json_answer())]]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(agent.RunRequest(mode="static", message="x"))

        second_turn = " ".join(
            str(message.get("content", "")) for message in stream.calls[1]
        )
        assert "NOTHING could be read" in second_turn
        assert "start with `{`" in second_turn
        assert "no markdown fence" in second_turn

    def test_a_compliant_answer_is_not_nudged(self, monkeypatch):
        stream = scripted_stream([[("content", json_answer())]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))
        assert not any(
            p["type"] == event_module.NOTICE and "required format" in p.get("text", "")
            for p in emitted
        )
        assert len(stream.calls) == 1

    def test_the_nudge_is_bounded_so_a_stubborn_model_still_finishes(self, monkeypatch):
        """A model that never complies must not loop: the run has to end, and the
        operator has to see what it did say."""
        stream = scripted_stream([[("content", "Just prose, forever.")] for _ in range(8)])
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, _ = agent.collect(agent.RunRequest(mode="static", message="x"))

        nudges = [
            p
            for p in emitted
            if p["type"] == event_module.NOTICE and "required format" in p.get("text", "")
        ]
        assert len(nudges) == agent.MAX_PROMPT_NUDGES
        assert emitted[-1]["type"] == event_module.RUN_FINISHED

    def test_a_prose_mode_is_not_nudged_for_prompts(self, monkeypatch):
        """`ideas` answers in prose by design, so the prompt nudge must not fire.

        It *does* get the research nudge — `ideas` is a research mode, and a run
        that proposes niches without looking anything up is the defect that guard
        exists for — so the script supplies a turn for each nudge to land on.
        """
        prose = "Here are three niches worth trying."
        stream = scripted_stream(
            [[("content", prose)] for _ in range(agent.MAX_TOOL_NUDGES + 1)]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, result = agent.collect(agent.RunRequest(mode="ideas", message="x"))
        assert not any(
            p["type"] == event_module.NOTICE and "required format" in p.get("text", "")
            for p in emitted
        )
        assert result["message"] == prose

    def test_a_validity_gated_run_is_not_nudged_for_prompts(self, monkeypatch):
        """The gate suppresses prompts on purpose, so demanding them would
        contradict the run's own objective."""
        stream = scripted_stream(
            [[("content", "The evidence is moderate. Continue, or research another idea?")]]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", validity_check=True)
        )
        assert not any(
            p["type"] == event_module.NOTICE and "required format" in p.get("text", "")
            for p in emitted
        )


# --------------------------------------------------------------------------- #
# The instructions themselves
# --------------------------------------------------------------------------- #

class TestToolInstructions:
    def test_every_tool_is_shown_with_a_literal_call_template(self):
        """A wrong argument name makes a call unparseable, and the model is far
        more reliable copying a shape than assembling one."""
        specs = tools.specs_for(wants_prompts=True, validity_check=True)
        rendered = prompts.tool_list_text(specs)
        for spec in specs:
            assert f'"name": "{spec["name"]}"' in rendered

    def test_required_arguments_are_marked_as_required(self):
        specs = tools.specs_for(wants_prompts=False, validity_check=False)
        rendered = prompts.tool_list_text(specs)
        assert "(REQUIRED)" in rendered

    def test_the_instructions_forbid_announcing_a_call_instead_of_making_it(self):
        """Measured live: the model replied "I'll research this niche before
        recording any confidence scores." and stopped."""
        text = prompts.RESEARCH_INSTRUCTION
        assert "Do not write \"I will search for" in text
        assert "Either emit the call, or answer" in text

    def test_the_instructions_state_the_answer_is_parsed_and_droppable(self):
        text = prompts.RESEARCH_INSTRUCTION
        assert "DISCARDED" in text
        assert "no result" in text

    def test_the_instructions_forbid_markup_in_the_final_answer(self):
        text = prompts.RESEARCH_INSTRUCTION
        assert "NO tool-call markup" in text

    def test_the_answer_format_marker_is_substituted(self):
        """An unsubstituted marker would reach the model as literal placeholder
        text, which is worse than no instruction at all."""
        system = prompts.compose_system_prompt(
            tool_specs=tools.specs_for(wants_prompts=True, validity_check=False),
            style_instruction="style",
            mode="static",
            validity_check=False,
            max_tools=10,
            wants_prompts=True,
            count=3,
        )
        assert "__ANSWER_FORMAT__" not in system
        assert "__TOOL_LIST__" not in system
        assert '"summary"' in system
        assert "3 entries" in system

    def test_a_prose_mode_gets_the_prose_answer_format(self):
        system = prompts.compose_system_prompt(
            tool_specs=tools.specs_for(wants_prompts=False, validity_check=False),
            style_instruction="style",
            mode="ideas",
            validity_check=False,
            max_tools=10,
            wants_prompts=False,
        )
        assert "ANSWER FORMAT" in system
        assert "plain prose" in system
        assert '"summary"' not in system

    def test_the_objectives_reference_the_answer_format(self):
        """The objective and the format block must agree; saying it in one place
        only is how a model answers in the other shape."""
        for mode, validity in (("static", False), ("batch", False), ("research", False)):
            objective = prompts._objective(mode, validity)
            assert "ANSWER FORMAT" in objective, mode

    def test_the_validity_objective_asks_for_prose(self):
        objective = prompts._objective("research", True)
        assert "prose format" in objective
        assert "Do NOT write the prompts yet" in objective


# --------------------------------------------------------------------------- #
# The malformed envelopes the gateway actually emits
#
# Every string in this class is copied from a live run's raw model content. The
# gateway does not reliably close the envelope the prompt asks for, and the first
# version of the parser required `</tool_call>`, so a *complete and valid* call was
# not recognised: the loop read the turn as a final answer and the run ended with
# no tool executed. That is the operator's "the agent suddenly stops without
# providing the prompts", and it is a parser fault — the arguments were all there.
# --------------------------------------------------------------------------- #

#: The DSML delimiter: two fullwidth vertical bars, ``DSML``, two more.
_BARS = "\uff5c\uff5c"
_DSML = f"<{_BARS}DSML{_BARS}"


def _dsml_open(keyword: str, attrs: str = "") -> str:
    return f"{_DSML}{keyword}{(' ' + attrs) if attrs else ''}>"


def _dsml_close(keyword: str = "") -> str:
    """A closing tag. The gateway is not consistent about the space after ``<``,
    so the default form includes one — as observed live."""
    return f"</{_BARS}DSML{_BARS} {keyword}>" if keyword else f"</{_BARS}DSML{_BARS}>"


#: A valid JSON body closed with DSML tags instead of ``</tool_call>``.
HYBRID_ENVELOPE = (
    '<tool_call>{"name": "market_overview", "arguments": {"niche": "cold storage '
    'freezer warehouse automation"}}' + _dsml_close("parameter")
    + _dsml_close("invoke") + _dsml_close("calls")
)

#: A hybrid whose JSON is **incomplete**, so no parser can recover it. Captured
#: live: the model truncated its own argument object mid-stream and then emitted
#: the DSML closing tags. This is the shape that genuinely cannot be executed, and
#: so the one that must produce a correction rather than a silent stop.
BROKEN_ENVELOPE = (
    '<tool_call>{"name": "market_overview", "arguments": {"niche": "cold storage'
    + _dsml_close("parameter") + _dsml_close("invoke") + _dsml_close("calls")
)

#: A pure DSML call that nests the whole argument object under one parameter.
NESTED_DSML = (
    _dsml_open("calls") + "\n"
    + _dsml_open("invoke", 'name="web_search"') + "\n"
    + _dsml_open("parameter", 'name="arguments" string="false"')
    + '{"query": "stock photo automated cold storage freezer warehouse robot ASRS"}'
    + _dsml_close("parameter") + "\n" + _dsml_close("invoke") + "\n"
    + _dsml_close("calls")
)

#: A pure DSML call in the documented per-argument shape.
PLAIN_DSML = (
    _dsml_open("calls") + "\n"
    + _dsml_open("invoke", 'name="web_search"') + "\n"
    + _dsml_open("parameter", 'name="query" string="true"') + "warehouse robots"
    + _dsml_close("parameter") + "\n" + _dsml_close("invoke") + "\n"
    + _dsml_close("calls")
)


class TestMalformedEnvelopesAreStillCalls:
    """A call the model *closed wrong* is still a call.

    The arguments are what matter. Refusing to execute a call whose JSON is
    complete and valid — because the closing tag is DSML rather than
    ``</tool_call>`` — throws away a correct turn and makes the run look like it
    stopped for no reason.
    """

    def test_a_body_closed_with_dsml_is_still_parsed(self):
        calls = protocol.parse_tool_calls(HYBRID_ENVELOPE)
        assert len(calls) == 1
        assert calls[0].name == "market_overview"
        assert calls[0].arguments["niche"] == "cold storage freezer warehouse automation"

    def test_the_spaced_closing_form_is_handled(self):
        """The gateway emits both ``<｜｜DSML｜｜`` and ``< ｜｜DSML｜｜``."""
        text = HYBRID_ENVELOPE.replace(_dsml_close("parameter"), f"</ {_BARS}DSML{_BARS} parameter>")
        calls = protocol.parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].name == "market_overview"

    def test_a_nested_arguments_parameter_is_unwrapped(self):
        """Otherwise a correct call arrives as ``{"arguments": {...}}`` — with no
        ``query`` of its own — and is rejected as malformed."""
        calls = protocol.parse_tool_calls(NESTED_DSML)
        assert len(calls) == 1
        assert calls[0].arguments == {
            "query": "stock photo automated cold storage freezer warehouse robot ASRS"
        }

    def test_the_per_argument_dsml_shape_still_works(self):
        calls = protocol.parse_tool_calls(PLAIN_DSML)
        assert len(calls) == 1
        assert calls[0].arguments == {"query": "warehouse robots"}

    def test_a_brace_inside_a_json_string_does_not_end_the_body(self):
        """The body is located by brace counting, not a regex, so a query that
        contains a brace or a quote cannot truncate the arguments."""
        text = (
            '<tool_call>{"name": "web_search", "arguments": {"query": '
            '"a \\"quoted\\" {braced} query"}}</tool_call>'
        )
        calls = protocol.parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0].arguments["query"] == 'a "quoted" {braced} query'

    def test_prose_that_merely_names_a_tool_is_not_a_call(self):
        """The opposite failure: the loop must still be able to terminate."""
        assert protocol.parse_tool_calls(
            "I will use web_search to look into this, and then explain what I found."
        ) == []


class TestNoMarkupEverReachesTheTranscript:
    """The operator reads the transcript as the agent's own words, so protocol
    markup must never survive into it — including the *malformed* envelopes, which
    are precisely the ones a ``</tool_call>``-keyed stripper leaves behind."""

    @pytest.mark.parametrize(
        "text",
        [HYBRID_ENVELOPE, NESTED_DSML, PLAIN_DSML],
        ids=["hybrid", "nested-dsml", "plain-dsml"],
    )
    def test_markup_is_stripped(self, text):
        stripped = protocol.strip_tool_calls(text)
        for token in ("tool_call", "DSML", _BARS, "parameter", "invoke"):
            assert token not in stripped, f"{token!r} leaked into {stripped!r}"

    def test_prose_around_a_malformed_call_is_kept(self):
        """The operator was reading that sentence; dropping it is a different bug."""
        text = "Let me check the market for this niche. " + HYBRID_ENVELOPE
        stripped = protocol.strip_tool_calls(text)
        assert "Let me check the market for this niche." in stripped
        assert "tool_call" not in stripped

    def test_an_incomplete_opener_is_treated_as_markup(self):
        """Captured live: the hold-back released ``name": "market_overview", …``
        into the transcript because ``<tool_call>`` was only matched once the whole
        marker had arrived."""
        assert agent._markup_index('name": "market_overview", "argu') is None
        assert agent._markup_index('<tool_call>{"name": "x"') is not None
        assert agent._markup_index("<tool") is not None
        assert agent._markup_index("a sentence ending in <tool_") is not None

    def test_a_partial_marker_inside_a_word_is_not_markup(self):
        """Otherwise ordinary prose would stop streaming mid-sentence."""
        assert agent._markup_index("the handsets are inside the crates") is None


class TestAMalformedCallIsNotAnEmptyReply:
    """The two faults need different counters and different corrections.

    Captured live: the model alternated between a correct call and a malformed
    hybrid, the malformed ones incremented the *empty* counter, and after two of
    them the run was finalised as "the model stopped producing usable output" —
    with four good tool results already gathered.
    """

    def test_a_malformed_reply_is_corrected_rather_than_counted_as_empty(
        self, monkeypatch, stub_search
    ):
        stub_search()
        # Turn 1: a malformed hybrid. Turn 2: the model complies.
        stream = scripted_stream(
            [
                [("content", HYBRID_ENVELOPE)],
                [
                    (
                        "content",
                        '<tool_call>{"name": "web_search", "arguments": {"query": "warehouse robots"}}</tool_call>',
                    )
                ],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)

        emitted, result = agent.collect(
            agent.RunRequest(mode="research", message="warehouse robots", max_tool_calls=6)
        )

        # The hybrid call now *runs* rather than being discarded, and the run
        # finishes normally with the model's own answer.
        assert any(p["type"] == event_module.TOOL_CALL for p in emitted)
        assert not any(
            p["type"] == event_module.NOTICE and "stopped producing usable output" in p.get("text", "")
            for p in emitted
        )
        assert emitted[-1]["status"] == "completed"

    def test_the_correction_names_the_real_fault(self, monkeypatch):
        """Telling a model "your reply was empty" when it wrote a call teaches it
        nothing. The correction has to name the mixing of formats."""
        stream = scripted_stream(
            [
                [("content", BROKEN_ENVELOPE)],
                [("content", BROKEN_ENVELOPE)],
                [("content", BROKEN_ENVELOPE)],
                [("content", BROKEN_ENVELOPE)],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=0)
        )
        corrections = [
            message["content"]
            for call in stream.calls[1:]
            for message in call
            if message.get("role") == "user" and "could not be read" in str(message.get("content"))
        ]
        assert corrections, "the malformed call was never corrected"
        assert "DSML" in corrections[0]
        # And it must not be described as an empty reply.
        assert "was empty" not in corrections[0]

    def test_a_malformed_call_does_not_exhaust_the_empty_counter(self, monkeypatch):
        """The counters are separate, so a run that alternates between a good call
        and a broken one keeps going instead of being finalised early."""
        stream = scripted_stream(
            [
                [("content", BROKEN_ENVELOPE)],
                [("content", '<tool_call>{"name": "web_search", "arguments": {"query": "q"}}</tool_call>')],
                [("content", BROKEN_ENVELOPE)],
                [("content", '<tool_call>{"name": "web_search", "arguments": {"query": "q2"}}</tool_call>')],
                [("content", json_answer())],
            ]
        )
        monkeypatch.setattr(agent, "stream_chat", stream)
        emitted, _ = agent.collect(
            agent.RunRequest(mode="research", message="x", max_tool_calls=6)
        )
        # Two malformed turns did not end the run: it still reached a real answer.
        assert not any(
            p["type"] == event_module.NOTICE
            and "stopped producing usable output" in p.get("text", "")
            for p in emitted
        )
        assert emitted[-1]["status"] == "completed"

    def test_a_genuinely_empty_reply_still_gets_its_own_message(self, monkeypatch):
        stream = scripted_stream([[("content", "")], [("content", "")], [("content", "")]])
        monkeypatch.setattr(agent, "stream_chat", stream)
        agent.collect(agent.RunRequest(mode="research", message="x", max_tool_calls=0))
        corrections = [
            message["content"]
            for call in stream.calls[1:]
            for message in call
            if message.get("role") == "user" and "was empty" in str(message.get("content"))
        ]
        assert corrections, "an empty reply should still be corrected as empty"
