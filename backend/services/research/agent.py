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
from services.research import context as context_module
from services.research import events as event_module
from services.research import protocol, synthesis, toolcall, tools
# Imported as a module because ``validity`` is also a key on a tool outcome; a
# by-name import of ``TARGET_AVERAGE`` would read as if it belonged to the outcome.
from services.research import sources as sources_module
from services.research import validity as validity_module

logger = logging.getLogger(__name__)

#: How many *research* tool calls one run may make (bookkeeping calls are free —
#: see :attr:`services.research.tools.Tool.consumes_budget`).
#:
#: Raised from 10, which was measurably too small. A single ``market_overview``
#: call spends **three** of them (it issues three queries), so a run that checks
#: two candidates for saturation and fetches one page had already spent eight
#: before it scored anything — and a gated run has to score, then possibly look
#: again for a stronger candidate, then write prompts. The cap was the binding
#: constraint on research quality, not the model's willingness to search.
#:
#: Still bounded, because the loop must terminate: this bounds work that can run
#: away (searches and page fetches), and the operator can raise it in Settings.
DEFAULT_MAX_TOOL_CALLS = 24

#: Bounds on the operator-configurable budget. The floor keeps a run from being
#: configured into uselessness; the ceiling keeps a looping model from running for
#: hours, which is the property the cap exists to guarantee.
MIN_TOOL_CALLS = 4
MAX_TOOL_CALLS = 80

#: Identical call repeated more than this many times is treated as a loop.
MAX_IDENTICAL_CALLS = 2

#: Turns without any tool call that are still not accepted as the final answer
#: (an empty reply). Prevents an empty reply from ending the run as "success".
MAX_EMPTY_REPLIES = 2

#: How many times a reply may contain tool-call markup that does not parse before
#: the run is finalised instead of being corrected again.
#:
#: Counted **separately** from :data:`MAX_EMPTY_REPLIES` because they are different
#: faults with different corrections. Captured live: the model alternated between a
#: correct call and a malformed hybrid (`<tool_call>{…}` closed with DSML tags), and
#: the malformed ones incremented the *empty* counter. After two of them the run was
#: finalised as "the model stopped producing usable output" — with four good tool
#: results already gathered — even though every one of those turns was a parse
#: failure that the correction prompt can fix.
MAX_MALFORMED_REPLIES = 2

#: How many times a gated run may be sent back to research a *stronger* candidate
#: before its answer is accepted as-is.
#:
#: The operator's instruction is that the collective average must clear the target,
#: because finding a better idea is the whole point of asking for one. The prompt
#: says so, but a prompt is a request, not a guarantee: measured live, a run
#: researched a replacement idea and returned **53%** — below the 72% of the idea
#: the operator had just rejected — and presented it as the answer, because nothing
#: in the loop compared the score to the target.
#:
#: Bounded because each attempt costs tool calls: a model that cannot find an 80%
#: idea would otherwise search until its budget was gone. When the attempts are
#: spent the run reports the best it found, with its real score.
MAX_TARGET_ATTEMPTS = 2

#: How many times a research run may be told "you announced research but did not
#: perform any" before its prose is accepted anyway.
#:
#: Measured live: asked to research a niche with the validity check on, the model
#: replied "I'll research this niche before recording any confidence scores." and
#: stopped. It had produced plain prose, so the loop correctly treated that as the
#: final answer — but the run had done no research at all. Nothing in the protocol
#: forces a tool call before an answer, so a *research* run needs the guard below.
MAX_TOOL_NUDGES = 2

#: How many times a *prompt-producing* run may be told "you did not return the
#: prompts" before its prose is accepted anyway.
#:
#: This is the fix for the operator's "the agent suddenly stops without providing
#: the prompts, especially in research mode". A prompt run has a hard requirement
#: the other modes do not: its answer must be the JSON contract, because that is
#: what the parser reads. Measured: with the instruction text saying "reply in
#: plain prose with no tool call at all. That is how you finish", a research run
#: would write a readable summary, parse to ZERO prompts, and be reported as a
#: clean success — a run that visibly did work and delivered nothing.
MAX_PROMPT_NUDGES = 2

#: Modes that produce prompts, and therefore get the format instruction and the
#: similarity tool. ``generate`` is the merged single/many mode; ``static`` and
#: ``batch`` are its legacy ids, still present so stored conversations keep
#: working.
PROMPT_MODES = frozenset({"static", "batch", "generate", "research"})

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
    validity_check: bool = False
    #: Prior conversation turns, oldest first, as ``{"role", "content"}`` dicts.
    history: list[dict] = field(default_factory=list)
    max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS
    temperature: float = 0.3
    #: The model's declared context window, used to decide when to fold the
    #: history. 0 disables folding, which is what a unit test wants.
    context_window: int = 0
    #: Set when this turn is the operator releasing the validity gate by pressing
    #: "Continue with these confidence rates".
    #:
    #: Needed because :attr:`wants_prompts` is otherwise computed from the mode and
    #: the gate alone, so a gated run could never be asked for prompts at all — the
    #: Continue button produced a second assessment instead of the prompts the
    #: operator had just asked for.
    released: bool = False
    #: The operator's priority sources, as a parsed
    #: :class:`services.research.sources.SourceSet` (or ``None``). Carried on the
    #: request rather than read from disk in the agent so a run is reproducible in
    #: a test and a mid-run file change cannot alter a turn already in flight.
    priority_sources: "sources_module.SourceSet | None" = None

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

        ``released`` is that continuation. Without it the gate was one-way: the
        operator's decision to proceed could never turn prompts back on.
        """
        if self.mode not in PROMPT_MODES or self.mode == "ideas":
            return False
        if self.released:
            return True
        return not self.validity_check


def _initial_messages(
    request: RunRequest, tool_specs: list[dict]
) -> tuple[list[dict], context_module.FoldedHistory]:
    """Build the conversation the model starts from, and fold it if it is too big.

    Returns ``(messages, folded)`` so the caller can report what was compacted.
    The history is passed through :func:`services.research.context.summarise_history`
    rather than sliced blindly: a fixed ``history[-12:]`` cannot know how large the
    turns are, and a dozen tool results can be far larger than the window. A
    conversation that overflows is truncated *from the front* by the provider,
    which removes the system prompt and leaves the model with no instructions —
    the failure the operator experiences as a run that stopped for no reason.
    """
    from services.research import prompts as prompt_module

    system = prompt_module.compose_system_prompt(
        tool_specs=tool_specs,
        mode=request.mode,
        validity_check=request.validity_check,
        max_tools=request.max_tool_calls,
        wants_prompts=request.wants_prompts,
        count=request.count,
        released=request.released,
        source_guidance=sources_module.guidance(request.priority_sources),
    )

    folded = context_module.summarise_history(
        request.history, window_tokens=request.context_window
    )

    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(folded.messages)

    user_text = (request.message or "").strip()
    if request.wants_prompts and request.count > 0:
        user_text += synthesis.prompt_format_instruction(request.count)
    messages.append({"role": "user", "content": user_text})
    return messages, folded


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

    messages, folded = _initial_messages(request, tool_specs)

    # Announce the context position up front, and again whenever it is measured,
    # so the operator can see how close the run is to the window instead of
    # discovering the limit by hitting it. Reported *after* folding, because that
    # is the size of the request actually being sent.
    context_report = context_module.window_report(
        messages, request.context_window, folded=folded
    )
    if folded.folded_turns:
        yield event_module.event(
            event_module.NOTICE,
            text=(
                f"This conversation had grown past the context window, so its "
                f"oldest {folded.folded_turns} turns were compacted into a "
                "summary. The most recent turns are kept in full."
            ),
        )
    if folded.note:
        yield event_module.event(event_module.NOTICE, text=folded.note)
    yield event_module.event(event_module.CONTEXT, **context_report.to_dict())

    accumulator = event_module.EventAccumulator()
    calls_made = 0
    #: How many tools ran at all, including the free bookkeeping ones.
    #:
    #: Tracked **separately** from ``calls_made`` because the two answer different
    #: questions: ``calls_made`` measures budget spent, ``calls_run`` measures
    #: whether the agent reached outside its own reasoning. The "you have not
    #: researched anything" guard needs the second. Conflating them was a real bug
    #: the moment bookkeeping tools became free: `assess_validity` stopped
    #: incrementing the budget, so the guard fired on a turn that *had* just run a
    #: tool and told the agent it had "only your own recall".
    calls_run = 0
    call_counts: dict[str, int] = {}
    empty_replies = 0
    malformed_replies = 0
    tool_nudges = 0
    prompt_nudges = 0
    target_attempts = 0
    truncated = False

    #: The best collective average recorded by an `assess_validity` call so far,
    #: or ``None`` when nothing has been scored. Tracked so the loop can tell
    #: whether the answer it is about to accept actually clears the operator's
    #: target — the prompt asks the model to keep searching, but only the loop can
    #: *enforce* it.
    best_average: float | None = None
    #: The subject of that best assessment, reported back to the operator when the
    #: attempts are spent so they know which idea the number belongs to.
    best_subject = ""

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
        # --- keep the turn inside the window --------------------------------- #
        # A single turn can add many large tool results, so a run that started
        # comfortably inside the window can push itself out of it. Measured live
        # with a small window: the final measurement reached 100%, and the next
        # request would have been truncated at the provider — losing the system
        # prompt, which is the failure this whole mechanism exists to prevent.
        messages, live_folded = context_module.compact_live_messages(
            messages, window_tokens=request.context_window
        )
        if live_folded.folded_turns:
            # Carry the in-run folding into the run's own history so the final
            # report describes the whole run, not just its opening turn.
            folded = context_module.FoldedHistory(
                messages=messages,
                summary=live_folded.summary,
                folded_turns=folded.folded_turns + live_folded.folded_turns,
                note=live_folded.note,
                degraded=folded.degraded or live_folded.degraded,
            )
            yield event_module.event(
                event_module.NOTICE,
                text=(
                    "This turn grew past the context window, so its earlier tool "
                    f"results ({live_folded.folded_turns} turns) were compacted "
                    "into a summary to make room. The most recent results are kept "
                    "in full."
                ),
            )
            live_report = context_module.window_report(
                messages, request.context_window, folded=folded
            )
            accumulator.add(
                event_module.event(event_module.CONTEXT, **live_report.to_dict())
            )
            yield event_module.event(event_module.CONTEXT, **live_report.to_dict())
        if live_folded.note:
            yield event_module.event(event_module.NOTICE, text=live_folded.note)

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
                # Two different faults reach this branch, and they need different
                # counters. A reply with *no* markup is a genuinely empty turn (a
                # reasoning model routinely emits one); a reply with markup that did
                # not parse is a malformed call, which the correction prompt below
                # can fix. Counting the second as the first is what ended a live run
                # after two malformed hybrids, with four good tool results already
                # gathered, under the message "the model stopped producing usable
                # output" — which was not what had happened.
                malformed = _looks_like_payload(reply)
                if malformed:
                    malformed_replies += 1
                else:
                    empty_replies += 1
                exhausted = (
                    malformed_replies > MAX_MALFORMED_REPLIES
                    if malformed
                    else empty_replies > MAX_EMPTY_REPLIES
                )
                if exhausted:
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
                            f"{empty_replies + malformed_replies} attempts. Showing "
                            "what was gathered before it stopped. Retrying the "
                            "request usually works."
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
                            "Your last reply contained tool-call markup that could not "
                            "be read, so nothing was executed and the turn was wasted. "
                            "The most common cause is mixing two formats: opening a "
                            "`<tool_call>` and closing it with something else.\n\n"
                            "Send the call again in EXACTLY this shape, on its own, "
                            "with nothing before it and nothing after it:\n"
                            '<tool_call>{"name": "tool_name", "arguments": '
                            '{"argument": "value"}}</tool_call>\n\n'
                            "Do not use DSML tags. Do not wrap it in a fence. Do not "
                            "add commentary. If you would rather stop researching, "
                            "reply with plain prose and no markup at all."
                            if malformed
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
            #
            # **Only on the opening turn.** `calls_run` counts this turn's calls,
            # but "you have no evidence" is a property of the whole conversation:
            # on a follow-up ("continue with this idea") the history already holds
            # every tool result from the earlier turns, so answering immediately is
            # correct. Firing here told the agent it had "only your own recall"
            # when it had a full transcript, and cost a turn correcting a model
            # that had done nothing wrong.
            if (
                request.mode in RESEARCH_MODES
                and calls_run == 0
                and not request.history
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

            # A gated run whose best score is below the operator's target has not
            # answered the question it was asked. The prompt tells the model to keep
            # searching, but a prompt is a request: measured live, a run researched a
            # replacement idea, scored it **53%** — below the 72% of the idea the
            # operator had just rejected — and presented it as the answer, because
            # nothing in the loop compared the score to the target.
            #
            # Only enforced when the gate is on and *not* released: a released run is
            # writing prompts for an idea the operator already accepted, so its score
            # is no longer the deciding question.
            if (
                request.validity_check
                and not request.wants_prompts
                and best_average is not None
                and best_average < validity_module.TARGET_AVERAGE
                and target_attempts < MAX_TARGET_ATTEMPTS
            ):
                target_attempts += 1
                yield event_module.event(
                    event_module.NOTICE,
                    text=(
                        f"The best idea so far scores {best_average:g}%, below the "
                        f"{validity_module.TARGET_AVERAGE:g}% target. Asking the agent "
                        "to research a stronger candidate."
                    ),
                )
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"The best idea you have assessed scores {best_average:g}%, "
                            f"which is below the {validity_module.TARGET_AVERAGE:g}% "
                            "target the operator set. Finding an idea that clears the "
                            "target is the whole point of this request.\n\n"
                            "Research a *different* candidate idea — a different "
                            "subject, setting or commercial use, not a rewording of "
                            "this one — and score it with `assess_validity` too, "
                            "including its `subject`. Keep going until one reaches the "
                            f"{validity_module.TARGET_AVERAGE:g}% target or you have "
                            f"tried {validity_module.MAX_CANDIDATES} distinct "
                            "candidates.\n\n"
                            "Do not invent a higher score to satisfy this. If no "
                            "candidate genuinely reaches the target, say so plainly, "
                            "report the best one with its real score, and explain what "
                            "the evidence is missing."
                        ),
                    }
                )
                continue

            # A *prompt-producing* run whose reply does not parse into prompts has
            # delivered nothing, however good it reads. This is the fix for "the
            # agent suddenly stops without providing the prompts": the run
            # completed, the transcript looked like work, and the prompt list was
            # empty because the answer was not the JSON contract.
            #
            # Checked here rather than after finalisation because the *reason* has
            # to reach the model while it can still act on it. A run that already
            # produced prompts is not nudged.
            if (
                request.wants_prompts
                and prompt_nudges < MAX_PROMPT_NUDGES
                and not synthesis.parse_prompts(prose)[0]
            ):
                prompt_nudges += 1
                yield event_module.event(
                    event_module.NOTICE,
                    text=(
                        "The agent answered without returning the prompts in the "
                        "required format, so nothing could be read from it. Asking "
                        "it to resend them."
                    ),
                )
                messages.append({"role": "assistant", "content": reply})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your reply did not contain the prompts in the required "
                            "format, so NOTHING could be read from it and the operator "
                            "received no prompts at all.\n\n"
                            "Reply again with ONLY the JSON object described in ANSWER "
                            "FORMAT. It must start with `{` and end with `}`. No prose "
                            "before it, no prose after it, no markdown fence, no "
                            "`<tool_call>` markup, no commentary about what you did.\n\n"
                            "If you already gathered the evidence you need, write the "
                            "JSON now. Do not call another tool."
                        ),
                    }
                )
                continue
            break

        if calls_made >= request.max_tool_calls:
            # Budget exhausted. Withhold the tools and demand an answer from what
            # has been gathered — far better than discarding the whole run.
            #
            # The notice names the budget and how to change it, because "the agent
            # reached its limit" is otherwise indistinguishable from a defect and
            # the operator has no way to know the number is theirs to raise.
            yield event_module.event(
                event_module.NOTICE,
                text=(
                    f"The agent reached its {request.max_tool_calls}-call research "
                    "limit and is answering with what it has gathered so far. "
                    "Raise the limit in Settings if runs need more research."
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

            # Validate *before* running, so an incomplete call is corrected rather
            # than executed against nothing. Measured live: a `market_overview`
            # call arrived with an empty `niche`, the tool answered "No niche
            # given", and the turn was spent — the model had "done the search" and
            # reasoned on from a result that said nothing about the subject.
            validation = toolcall.validate_arguments(
                call.name,
                call.arguments,
                tool_registry[call.name].parameters,
            )
            if not validation.ok:
                result_texts.append(
                    protocol.format_tool_result(call.name, validation.text, error=True)
                )
                yield event_module.event(
                    event_module.TOOL_RESULT,
                    name=call.name,
                    summary=(
                        "Rejected — missing "
                        + ", ".join(validation.missing)
                    ),
                    ok=False,
                )
                # Deliberately NOT counted against the budget: the call never ran,
                # and charging for it would let a model burn a run on retries.
                continue

            # Charge only the tools that reach outside the process for evidence.
            # `assess_validity` and `check_prompt_similarity` only record what the
            # model has already worked out, and charging for them starved the very
            # quality mechanism the budget exists to serve: measured live, a run
            # spent its final call on `assess_validity`, the loop then judged the
            # score below target and asked for a stronger candidate with nothing
            # left to look with.
            calls_run += 1
            if tool_registry[call.name].consumes_budget:
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
                # Presented through the SAME builder the stored result uses.
                # The tool returns the raw assessment (scores + subject + target),
                # which has no `meets_target`, `collective_band`, `recommendation`
                # or `disclaimer`. Measured live: the streaming card read
                # "Reaches the 80% target." for an idea scoring 73.5, because an
                # absent `meets_target` is falsy-but-`undefined` and the card's
                # `undefined ? … : …` fell through to the below-target wording while
                # `target_average` rendered as `undefined%` — and the recommendation
                # and the mandatory disclaimer rendered as *nothing at all*.
                presented = _present_validity(outcome.validity)
                # Tracked from the PRESENTED average, so the target-seeking nudge
                # below compares the same number the operator was just shown.
                try:
                    scored = float(presented.get("collective_average"))
                except (TypeError, ValueError):
                    scored = None
                if scored is not None and (best_average is None or scored > best_average):
                    best_average = scored
                    best_subject = str(presented.get("subject") or "").strip()
                yield event_module.event(
                    event_module.VALIDITY,
                    validity=presented,
                    follow_up_actions=list(_follow_up_actions(request.mode)),
                )

        messages.append({"role": "user", "content": "\n\n".join(result_texts)})

    # --- finish ------------------------------------------------------------- #
    # Always re-strip: `prose` is assigned per turn, and a turn that produced
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

    # Re-measure now that every tool result is in the conversation, so the
    # indicator reflects the size of the request that was actually sent rather
    # than its opening size.
    final_report = context_module.window_report(
        messages, request.context_window, folded=folded
    )
    accumulator.add(event_module.event(event_module.CONTEXT, **final_report.to_dict()))
    yield event_module.event(event_module.CONTEXT, **final_report.to_dict())

    yield event_module.event(
        event_module.RUN_FINISHED,
        status="completed",
        answer=synthesis.answer_text(answer),
        thinking=accumulator.thinking,
    )


def _present_validity(assessment: dict) -> dict:
    """The assessment as the operator's card needs it, or the raw dict as a fallback.

    The tool returns the *raw* assessment. Everything the card displays beyond the
    two numbers — `meets_target`, `collective_band`, `collective_label`,
    `recommendation` and the mandatory `disclaimer` — is derived by
    :func:`services.research.validity.describe`, which the storage path already
    calls. Building the event from the raw dict instead meant the live card and the
    reopened card disagreed: measured live, a streaming card showed no
    recommendation and no disclaimer at all.

    Falls back to the raw assessment so a malformed one degrades to "the numbers
    still arrive" rather than losing the event entirely.
    """
    from services.research import validity as validity_module

    view = validity_module.describe(assessment)
    return view.to_dict() if view is not None else assessment


def _follow_up_actions(mode: str) -> tuple[dict, ...]:
    """The post-assessment choices, from the validity module.

    Imported lazily to keep the agent module free of a module-level cycle
    through the tool registry.

    ``mode`` decides the wording, not this turn's ``wants_prompts``: a gated
    research run reports ``wants_prompts`` false *because of the gate*, and would
    otherwise be offered the no-prompts button even though continuing is exactly
    what turns its prompts on.

    The predicate deliberately mirrors the first clause of
    :attr:`RunRequest.wants_prompts` so the two cannot disagree about which modes
    write prompts.
    """
    from services.research.validity import follow_up_actions

    return follow_up_actions(can_produce_prompts=mode in PROMPT_MODES and mode != "ideas")


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
#: An opener that is *incomplete* at the end of the buffer: ``<tool`` is the start
#: of ``<tool_call>``, and treating it as prose streams half a marker. Captured
#: live: the model wrote ``<tool_call>{"name": "market_overview", …`` and then
#: closed it with DSML tags, so the hold-back released the opening brace and the
#: operator saw `name": "market_overview", "arguments": …` as the agent's answer.
_PARTIAL_MARKERS = ("<tool", "<tool_", "<tool_c", "<tool_ca", "<tool_cal", "dsm", "ds")
_MARKUP_TAIL = 32


def _markup_index(text: str) -> int | None:
    """Index of the earliest tool-call marker in ``text``, or ``None``.

    An index rather than a boolean so the caller can keep the *prose* that came
    before the marker and discard only the markup. Dropping the whole buffer would
    lose a sentence the operator was already reading — "Let me look at the market
    data. <tool_call>…" would arrive with its first sentence missing.

    A *partial* marker counts. An earlier version only matched complete markers, so
    a reply whose opener never completed (`<tool_call>{"name": …` followed by DSML
    tags) had its brace-and-quote released into the transcript as prose.
    """
    lowered = text.lower()
    found = [lowered.find(marker) for marker in _MARKUP_MARKERS]
    positions = [position for position in found if position != -1]
    if positions:
        return min(positions)

    # Only a *trailing* partial marker is one: a `ds` in the middle of a word is
    # prose ("inside", "handsets"), but a `ds` at the very end may be the start of
    # `dsml` arriving in the next delta.
    for marker in _PARTIAL_MARKERS:
        if lowered.endswith(marker):
            return len(text) - len(marker)
    return None


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
