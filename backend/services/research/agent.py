"""The research agent loop.

The loop is hand-rolled because the configured gateway does not support OpenAI
tool calling (verified — see :mod:`services.research.protocol`). Each turn is:

1. stream the model's reply, forwarding reasoning and prose to the UI as it
   arrives;
2. parse any tool calls out of the completed reply;
3. if there are none, that reply *is* the answer — finish;
4. otherwise run each call, emit the result, append it to the conversation and
   turn again.

Three properties the loop has to guarantee, because each of them has a failure
mode that is invisible without care:

* **It always terminates.** A model that calls a tool on every turn would loop
  forever, so there is a hard call budget; when it is exhausted the loop asks for
  a final answer with tools withheld and, if the model still calls one, keeps the
  prose it wrote. A run that hits the cap says so.
* **A refusal is never silently an empty result.** Every tool outcome carries its
  own failure text into the conversation, so the model cannot conclude "nothing
  exists" from a blocked search.
* **Repeated identical calls are not repeated.** A model stuck re-running one
  query gets told it already has that result, which breaks the loop far more
  cheaply than waiting for the budget to run out.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator

from services.llm_client import LLMError, LLMTruncatedError, stream_chat
from services.research import events as event_module
from services.research import protocol, synthesis, tools

logger = logging.getLogger(__name__)

#: How many tool calls one run may make. Enough for a genuine multi-source
#: investigation, small enough that a looping model cannot run for hours.
DEFAULT_MAX_TOOL_CALLS = 10

#: Identical call repeated more than this many times is treated as a loop.
MAX_IDENTICAL_CALLS = 2

#: Turns without any tool call that are still not accepted as the final answer
#: (an empty reply). Prevents an empty reply from ending the run as "success".
MAX_EMPTY_REPLIES = 2

#: How many times a research run may be told "you announced research but did not
#: perform any" before its prose is accepted anyway.
#:
#: Measured live: asked to research a niche with the validity check on, the model
#: replied "I'll research this niche before recording any confidence scores." and
#: stopped. It had produced plain prose, so the loop correctly treated that as the
#: final answer — but the run had done no research at all. Nothing in the protocol
#: forces a tool call before an answer, so a *research* run needs the guard below.
MAX_TOOL_NUDGES = 2

#: Modes that produce prompts, and therefore get the format instruction and the
#: similarity tool.
PROMPT_MODES = frozenset({"static", "batch", "research"})

#: Modes whose whole point is research, so the agent must actually search before
#: it may answer. A `static` run is exempt: the operator's hint is the authority
#: on the subject, and refusing to answer without a search would add latency to
#: the one mode that does not need it.
RESEARCH_MODES = frozenset({"research", "ideas"})


@dataclass
class RunRequest:
    """Everything one run needs. Kept as data so a run is reproducible in a test."""

    mode: str
    message: str
    count: int = 1
    style_instruction: str = ""
    validity_check: bool = False
    #: Prior conversation turns, oldest first, as ``{"role", "content"}`` dicts.
    history: list[dict] = field(default_factory=list)
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    temperature: float = 0.3

    @property
    def wants_prompts(self) -> bool:
        """Whether this run should end with concrete prompts.

        ``ideas`` does not: it proposes niches and stops, because the operator
        picks one before any prompt is written. Generating prompts there would
        answer a question that was not asked.

        **The validity gate also suppresses prompts**, and this is not cosmetic.
        With the gate on, the agent is instructed to research, score, and then
        *stop* so the operator can decide. Asking it for prompts at the same time
        is a direct contradiction — the model detected it and said so in its own
        reasoning ("Wait, there's a conflict"), then emitted a malformed turn
        because it could not satisfy both. Gating here makes the two instructions
        agree: no format block, and no similarity tool, until the operator
        continues and prompts are actually wanted.
        """
        if self.mode not in PROMPT_MODES or self.mode == "ideas":
            return False
        return not self.validity_check


def _initial_messages(request: RunRequest, tool_specs: list[dict]) -> list[dict]:
    """Build the conversation the model starts from."""
    from services.research import prompts as prompt_module

    system = prompt_module.compose_system_prompt(
        tool_specs=tool_specs,
        style_instruction=request.style_instruction or prompt_module.DEFAULT_STYLE_INSTRUCTION,
        mode=request.mode,
        validity_check=request.validity_check,
        max_tools=request.max_tool_calls,
    )

    messages: list[dict] = [{"role": "system", "content": system}]

    # A bounded slice of the transcript: enough for the operator to say "that
    # second idea" or "yes, continue", not enough to crowd out the system prompt.
    for turn in request.history[-12:]:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    user_text = (request.message or "").strip()
    if request.wants_prompts and request.count > 0:
        user_text += synthesis.prompt_format_instruction(request.count)
    messages.append({"role": "user", "content": user_text})
    return messages


def _final_answer_prompt(reason: str) -> dict:
    """A user-role nudge that asks for the answer with no tools available."""
    return {
        "role": "user",
        "content": (
            f"{reason}\n"
            "Do not call any more tools. Answer now, in plain prose, using only "
            "what you have already gathered. If the evidence is incomplete, say so."
        ),
    }


def _messages_without_tools(messages: list[dict], note: str) -> list[dict]:
    """A copy of the conversation whose system prompt advertises no tools.

    Withholding the tool list is what actually stops a model from calling one —
    a polite instruction not to is not enough for a model that has just spent
    several turns calling tools.
    """
    if not messages:
        return []
    head = str(messages[0].get("content") or "")
    without_tools = head.split("TOOLS YOU HAVE")[0]
    return [
        {"role": "system", "content": f"{without_tools}TOOLS YOU HAVE\n(none — {note})"},
        *messages[1:],
    ]


def _answer_without_tools(
    request: RunRequest, messages: list[dict]
) -> tuple[str, list[str]]:
    """Ask for a final answer with the tools withheld.

    Returns ``(prose, thinking_chunks)``. The reasoning is *returned* rather than
    yielded so this stays a plain function: a generator would have to be consumed
    by the caller, and every call site here wants the finished answer, not a
    stream. The caller emits the thinking events itself.

    Returns empty prose when even this turn produces nothing usable, so the caller
    can decide what to report. A failed turn is never raised: a run that has
    already gathered evidence must still finish.
    """
    collected: list[str] = []
    thinking: list[str] = []
    try:
        for kind, text in stream_chat(messages, temperature=request.temperature):
            if kind == "thinking":
                thinking.append(text)
            else:
                collected.append(text)
    except Exception:  # noqa: BLE001 - reported by the caller as a missing answer
        return protocol.strip_tool_calls("".join(collected)), thinking
    return protocol.strip_tool_calls("".join(collected)), thinking


def run(request: RunRequest) -> Iterator[dict]:
    """Run the agent, yielding events.

    A generator rather than a callback list so the caller can stream each event
    the moment it happens and, if the client disconnects, simply stop iterating —
    the loop needs no cancellation flag to notice.

    Yields:
        Event dicts from :mod:`services.research.events`. Always ends with
        ``run_finished``, whatever happened, so a consumer never waits forever.
    """
    tool_registry = tools.registry_for(
        wants_prompts=request.wants_prompts, validity_check=request.validity_check
    )
    tool_specs = [tool.spec() for tool in tool_registry.values()]

    yield event_module.event(
        event_module.RUN_STARTED,
        mode=request.mode,
        count=request.count,
        validity_check=request.validity_check,
        wants_prompts=request.wants_prompts,
        tools=sorted(tool_registry),
        max_tool_calls=request.max_tool_calls,
    )

    messages = _initial_messages(request, tool_specs)
    accumulator = event_module.EventAccumulator()
    calls_made = 0
    call_counts: dict[str, int] = {}
    empty_replies = 0
    tool_nudges = 0
    truncated = False

    #: A prompt-producing run answers in the JSON contract, so its content deltas
    #: are a machine payload, not prose. Streaming them would print raw JSON with
    #: escaped newlines into the transcript, and the prompt cards present the same
    #: information properly. The reasoning and the tool steps still stream live.
    stream_prose = not request.wants_prompts

    #: Prose written on the turn that produced the final answer. Kept in a
    #: variable (not read off the accumulator) because the accumulator is fed
    #: only by the finalisation events, so an early exit would otherwise report
    #: no answer at all.
    prose = ""

    while True:
        # --- stream one turn ------------------------------------------------ #
        thinking_buffer: list[str] = []
        content_buffer: list[str] = []
        #: Content not yet released to the transcript. Held back so a tool-call
        #: marker split across two deltas cannot leak its first half as prose —
        #: without the hold-back, "…let me look <tool" reaches the operator and the
        #: rest is suppressed, which reads as a truncated sentence.
        pending = ""
        #: Latched once the turn reveals itself to be a tool call. From then on the
        #: content is protocol, not the agent's words, and must not be streamed.
        markup_seen = False
        stream_error = ""

        try:
            for kind, text in stream_chat(
                messages, temperature=request.temperature
            ):
                if kind == "thinking":
                    thinking_buffer.append(text)
                    # Feed the accumulator as the tokens arrive so the run's
                    # reasoning survives even if the stream later fails.
                    accumulator.add(event_module.event(event_module.THINKING, text=text))
                    yield event_module.event(event_module.THINKING, text=text)
                    continue

                content_buffer.append(text)
                pending += text
                marker_at = _markup_index(pending)
                if marker_at is not None:
                    # Keep the prose the operator has already started reading and
                    # drop everything from the marker onward: that is the protocol.
                    head = pending[:marker_at]
                    if stream_prose and head.strip():
                        yield event_module.event(event_module.MESSAGE, text=head)
                    pending = ""
                    markup_seen = True
                elif stream_prose and len(pending) > _MARKUP_TAIL:
                    # Release everything except the hold-back window.
                    release = pending[:-_MARKUP_TAIL]
                    pending = pending[-_MARKUP_TAIL:]
                    yield event_module.event(event_module.MESSAGE, text=release)
        except LLMTruncatedError as exc:
            # A reasoning model that spent its whole budget thinking returns no
            # content. Matched by *type* rather than by words in the message: the
            # old substring test also caught a 401 whose text happened to contain
            # "empty", which turned a configuration fault into a silent truncation
            # and dropped the error entirely.
            stream_error = str(exc)
            truncated = True
            yield event_module.event(
                event_module.NOTICE,
                text=(
                    "The model used its whole token budget without producing an "
                    "answer. The run was cut short; retrying usually works."
                ),
            )
        except LLMError as exc:
            stream_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - a provider fault must end the run cleanly
            stream_error = f"{type(exc).__name__}: {exc}"

        reply = "".join(content_buffer)
        thinking = "".join(thinking_buffer)

        # Release any prose still inside the hold-back window. Doing it here — after
        # the whole turn is known — is what makes the hold-back safe: by now the
        # marker question is settled, so text that looked like the start of a tool
        # call but never became one is not lost.
        if stream_prose and pending and not markup_seen:
            yield event_module.event(event_module.MESSAGE, text=pending)

        if stream_error and not truncated:
            yield event_module.event(event_module.ERROR, text=stream_error)
            yield event_module.event(
                event_module.RUN_FINISHED,
                status="error",
                answer=protocol.strip_tool_calls(prose),
                thinking=accumulator.thinking,
            )
            return

        # --- decide: tool call or final answer ------------------------------ #
        calls = protocol.parse_tool_calls(reply)
        prose = protocol.strip_tool_calls(reply)

        if not calls:
            if not prose.strip():
                # A turn with no usable prose is retried before it is treated as a
                # fault. The threshold is deliberately above one: a reasoning model
                # routinely emits a thinking-only turn, and failing the whole run on
                # the first one is what produced "The model stopped producing any
                # output" after the agent had already gathered its evidence.
                empty_replies += 1
                if empty_replies > MAX_EMPTY_REPLIES:
                    # Do NOT discard the run. By this point the agent may have
                    # already gathered its evidence, and an earlier version
                    # returned an error here — throwing away a completed research
                    # turn because the final phrasing turn misbehaved, which the
                    # operator experiences as a spinner that ends in nothing.
                    # Finalise instead: the transcript, the tool steps and any
                    # answer recovered from the transcript are all still useful.
                    yield event_module.event(
                        event_module.NOTICE,
                        text=(
                            "The model stopped producing usable output after "
                            f"{empty_replies} attempts. Showing what was gathered "
                            "before it stopped. Retrying the request usually works."
                        ),
                    )
                    recovered = _last_prose(accumulator, messages)
                    if not recovered.strip():
                        # Nothing usable was recovered, and the run has already
                        # gathered evidence. Asking once more with the tools
                        # withheld turns that evidence into the operator's answer;
                        # ending here instead would show the research steps and
                        # then nothing, which is what "a spinner that ends in
                        # silence" means. The loop cannot repeat: this branch
                        # returns unconditionally.
                        yield event_module.event(
                            event_module.NOTICE,
                            text=(
                                "Asking the model for a conclusion from the "
                                "evidence already gathered."
                            ),
                        )
                        recovered, rescue_thinking = _answer_without_tools(
                            request,
                            _messages_without_tools(
                                messages,
                                "answer from the evidence already gathered",
                            ),
                        )
                        for chunk in rescue_thinking:
                            accumulator.add(
                                event_module.event(event_module.THINKING, text=chunk)
                            )
                            yield event_module.event(event_module.THINKING, text=chunk)
                    for payload in _finalise(request, recovered, True):
                        accumulator.add(payload)
                        yield payload
                    yield event_module.event(
                        event_module.RUN_FINISHED,
                        status="completed" if recovered.strip() else "error",
                        answer=synthesis.answer_text(recovered),
                        thinking=accumulator.thinking,
                    )
                    return
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your last reply contained a tool call that could not be "
                            "parsed, so it was discarded. Reply with either exactly "
                            'this shape — <tool_call>{"name": "tool_name", '
                            '"arguments": {"argument": "value"}}</tool_call> — or with '
                            "plain prose and no tool markup at all."
                            if _looks_like_payload(reply)
                            else "Your last reply was empty. Please answer."
                        ),
                    }
                )
                continue

            # A *research* run that answers without calling a single tool has not
            # researched anything — it answered from the model's recall, which is
            # exactly what this feature exists to replace. Measured live: asked to
            # research a niche, the model replied "I'll research this niche before
            # recording any confidence scores." and stopped, announcing research it
            # never performed. The prose is a valid final answer as far as the
            # protocol is concerned, so the guard has to live here.
            if (
                request.mode in RESEARCH_MODES
                and calls_made == 0
                and tool_nudges < MAX_TOOL_NUDGES
            ):
                tool_nudges += 1
                yield event_module.event(
                    event_module.NOTICE,
                    text=(
                        "The agent tried to answer without researching anything. "
                        "Asking it to use its tools first."
                    ),
                )
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have not called any tools yet, so you have no "
                            "evidence — only your own recall. This task requires "
                            "research. Call `web_search` or `market_overview` now, "
                            "and only answer once you have results to reason from. "
                            "Do not describe what you are about to do; do it."
                        ),
                    }
                )
                continue
            break

        if calls_made >= request.max_tool_calls:
            # Budget exhausted. Withhold the tools and demand an answer from what
            # has been gathered — far better than discarding the whole run.
            yield event_module.event(
                event_module.NOTICE,
                text=(
                    f"The agent reached its {request.max_tool_calls}-call limit and "
                    "is answering with what it has gathered so far."
                ),
            )
            messages.append({"role": "assistant", "content": prose or reply})
            messages.append(
                _final_answer_prompt("You have used your whole tool budget.")
            )
            # One last turn with no tools described, so the model cannot call one.
            final_messages = _messages_without_tools(
                messages, "your budget is spent; answer from what you have"
            )
            final_prose, final_thinking = _answer_without_tools(request, final_messages)
            for chunk in final_thinking:
                accumulator.add(event_module.event(event_module.THINKING, text=chunk))
                yield event_module.event(event_module.THINKING, text=chunk)
            if not final_prose:
                yield event_module.event(
                    event_module.NOTICE,
                    text="The final answer attempt produced no usable text.",
                )
            # The final turn's prose supersedes the tool-call reply it replaced.
            if final_prose.strip():
                prose = final_prose
            break

        # --- run the calls -------------------------------------------------- #
        messages.append({"role": "assistant", "content": reply})
        result_texts: list[str] = []

        for call in calls:
            signature = f"{call.name}:{sorted(call.arguments.items())}"
            call_counts[signature] = call_counts.get(signature, 0) + 1

            yield event_module.event(
                event_module.TOOL_CALL,
                name=call.name,
                arguments=call.arguments,
                summary=event_module.summarise_tool_call(call.name, call.arguments),
            )

            if call_counts[signature] > MAX_IDENTICAL_CALLS:
                # Breaking the loop explicitly: repeating a call cannot produce
                # new information, and waiting for the budget to expire would
                # just waste time before the same answer.
                text = (
                    f"<tool_result name=\"{call.name}\" error=\"true\">\n"
                    "You have already run this exact call and have its result. "
                    "Use the information you have, or make a different call.\n"
                    "</tool_result>"
                )
                result_texts.append(text)
                yield event_module.event(
                    event_module.TOOL_RESULT,
                    name=call.name,
                    summary="Repeated call — skipped",
                    ok=False,
                )
                continue

            if call.name not in tool_registry:
                text = protocol.format_call_error(
                    call.name,
                    f"there is no tool called {call.name!r}",
                    sorted(tool_registry),
                )
                result_texts.append(text)
                yield event_module.event(
                    event_module.TOOL_RESULT,
                    name=call.name,
                    summary=f"Unknown tool {call.name!r}",
                    ok=False,
                )
                continue

            calls_made += 1
            started = time.time()
            outcome = tools.call_tool(tool_registry, call.name, call.arguments)
            result_texts.append(
                protocol.format_tool_result(call.name, outcome.text or "(no output)")
            )

            yield event_module.event(
                event_module.TOOL_RESULT,
                name=call.name,
                summary=outcome.summary,
                ok=not outcome.degraded,
                duration_seconds=round(time.time() - started, 2),
            )

            if outcome.sources:
                yield event_module.event(event_module.SOURCES, sources=outcome.sources)
            if outcome.validity:
                yield event_module.event(
                    event_module.VALIDITY,
                    validity=outcome.validity,
                    follow_up_actions=list(_follow_up_actions()),
                )

        messages.append({"role": "user", "content": "\n\n".join(result_texts)})

    # --- finish ------------------------------------------------------------- #    # Always re-strip: `prose` is assigned per turn, and a turn that produced
    # tool calls keeps its markup in that variable. Without this the raw
    # `<tool_call>{…}</tool_call>` text is persisted as the run's answer and
    # rendered in the transcript.
    answer = protocol.strip_tool_calls(prose)
    if not answer:
        # Every turn produced only tool calls, or the last reply was empty after
        # a stream error. Fall back to the accumulated prose so the operator gets
        # whatever the model did say.
        answer = _last_prose(accumulator, messages)

    for payload in _finalise(request, answer, truncated):
        accumulator.add(payload)
        yield payload

    yield event_module.event(
        event_module.RUN_FINISHED,
        status="completed",
        answer=synthesis.answer_text(answer),
        thinking=accumulator.thinking,
    )

def _follow_up_actions() -> tuple[dict, ...]:
    """The post-assessment choices, from the validity module.

    Imported lazily to keep the agent module free of a module-level cycle
    through the tool registry.
    """
    from services.research.validity import FOLLOW_UP_ACTIONS

    return FOLLOW_UP_ACTIONS


def _last_prose(accumulator: event_module.EventAccumulator, messages: list[dict]) -> str:
    """Recover the model's prose from the transcript as a last resort."""
    for message in reversed(messages):
        if message.get("role") == "assistant":
            cleaned = protocol.strip_tool_calls(str(message.get("content") or ""))
            if cleaned.strip():
                return cleaned.strip()
    return accumulator.message


#: A tool-call opener can be split across deltas (``<tool_`` then ``call>``), so the
#: check runs on the turn's content *so far* and the streaming loop holds back a
#: tail of this length before releasing text.
_MARKUP_MARKERS = ("<tool_call", "dsml")
_MARKUP_TAIL = 32


def _markup_index(text: str) -> int | None:
    """Index of the earliest tool-call marker in ``text``, or ``None``.

    An index rather than a boolean so the caller can keep the *prose* that came
    before the marker and discard only the markup. Dropping the whole buffer would
    lose a sentence the operator was already reading — "Let me look at the market
    data. <tool_call>…" would arrive with its first sentence missing.
    """
    lowered = text.lower()
    found = [lowered.find(marker) for marker in _MARKUP_MARKERS]
    positions = [position for position in found if position != -1]
    return min(positions) if positions else None


def _has_markup(text: str) -> bool:
    """Whether any content seen so far contains tool-call markup.

    Used to stop streaming a turn's content the moment the model starts emitting a
    tool call. Without it the markup is accumulated as the run's *transcript* and
    the raw `<tool_call>{…` text is rendered to the operator as the agent's
    answer — measured live on a research run with the validity gate on, where the
    gate makes ``wants_prompts`` false and therefore re-enabled content streaming.
    """
    return _markup_index(text) is not None


def _looks_like_payload(reply: str) -> bool:
    """Whether a reply contained tool-call markup that could not be parsed.

    Measured live: the model emitted a hybrid — it opened a JSON ``<tool_call>``
    and switched mid-stream to DeepSeek's DSML envelope — which the protocol
    cannot parse. The stripped result was empty, so the loop treated the turn as
    a silent model and told it "your reply was empty", which is both untrue and
    useless as a correction. Recognising the markup lets the retry name the real
    fault, and lets the run be finalised instead of thrown away.
    """
    return _has_markup(reply or "")


def _finalise(
    request: RunRequest, answer: str, truncated: bool
) -> Iterator[dict]:
    """Emit the derived results of a finished run.

    Prompts are only extracted when the run was asked for them, and the reason is
    surfaced rather than the run being reported as a clean success — an operator
    who asked for six prompts and got two needs to know why.
    """
    if not request.wants_prompts:
        # Returning rather than yielding would make this a plain function, so the
        # caller's `for … in _finalise(...)` would raise instead of iterating zero
        # events. An explicit unreachable yield keeps it a generator on every path.
        if False:  # pragma: no cover
            yield
        return

    drafts, pairs, note, summary = synthesis.build_drafts(answer)

    if note:
        yield event_module.event(event_module.NOTICE, text=note)
    if truncated and not drafts:
        yield event_module.event(
            event_module.NOTICE,
            text=(
                "No prompts could be extracted because the model's answer was cut "
                "short. Try again — a reasoning model sometimes needs a second run."
            ),
        )
        return
    if not drafts:
        return

    if pairs:
        yield event_module.event(
            event_module.NOTICE,
            text=(
                f"{len(pairs)} of the returned prompts overlap heavily. They are "
                "shown but not pre-selected, because near-identical prompts become "
                "near-identical images and Adobe refuses similar content."
            ),
        )

    flagged = sum(1 for draft in drafts if draft.warnings)
    if flagged:
        yield event_module.event(
            event_module.NOTICE,
            text=f"{flagged} prompt(s) have house-rule warnings — review them before saving.",
        )

    yield event_module.event(
        event_module.PROMPTS,
        prompts=[draft.to_dict() for draft in drafts],
        summary=summary,
        duplicate_pairs=[
            {"left": left, "right": right, "score": score} for left, right, score in pairs
        ],
        saveable=synthesis.saveable_prompts(drafts),
    )


def collect(request: RunRequest) -> tuple[list[dict], dict]:
    """Run to completion, returning ``(events, derived_result)``.

    For the non-streaming path and for tests. The streaming endpoint uses
    :func:`run` directly.
    """
    emitted: list[dict] = []
    accumulator = event_module.EventAccumulator()
    for payload in run(request):
        emitted.append(payload)
        accumulator.add(payload)
    return emitted, accumulator.to_dict()


def is_prompt_run(mode: str) -> bool:
    """Whether a mode produces prompts. Exposed for the router's validation."""
    return mode in PROMPT_MODES
