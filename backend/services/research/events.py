"""The streamed event vocabulary of a research run.

The UI needs to show a run *as it happens*: the model's reasoning token by token,
each site it opens, and the final answer. A single request/response cannot do
that, so a run emits a typed event stream.

Every event is a plain dict with a ``type`` — no framework, no schema coupling —
so the same list can be:

* streamed over SSE while the run is live,
* persisted and replayed when the operator reopens the conversation,
* asserted against in tests without an HTTP client.

Event types
-----------
``run_started``   the run began; carries the mode and settings actually used.
``thinking``      a chunk of the model's reasoning, to render live and collapse.
``message``       a chunk of the model's *visible* prose.
``tool_call``     the agent requested a tool, with the arguments it chose.
``tool_result``   that tool finished, with a short human-readable summary.
``sources``       the web sources gathered so far (drives the sources panel).
``prompts``       the finished prompts (drives the prompt cards).
``validity``      the confidence assessment, when the validity check ran.
``context``       how full the model's context window is, and whether the
                  conversation was compacted to fit it (drives the live bar).
``notice``        something the operator must know (a degraded search, a
                  truncated reply). Rendered distinctly from the answer.
``error``         the run failed; carries a message.
``run_finished``  terminal event; the UI stops streaming on it.

Ordering guarantee: ``run_finished`` is always the last event of a run, and it is
emitted on every path — success, failure and cancellation — so a client can never
wait forever on a stream that has already stopped producing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

#: Used by the accumulator to report a dropped, malformed source entry. A
#: per-run failure is a warning, not an error: the run still completes.
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Event type names
# --------------------------------------------------------------------------- #

RUN_STARTED = "run_started"
THINKING = "thinking"
MESSAGE = "message"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
SOURCES = "sources"
PROMPTS = "prompts"
VALIDITY = "validity"
CONTEXT = "context"
NOTICE = "notice"
ERROR = "error"
RUN_FINISHED = "run_finished"

#: Terminal events. A stream that has emitted one of these is complete.
TERMINAL_TYPES = frozenset({RUN_FINISHED, ERROR})

#: Every type a client may receive, for validation.
ALL_TYPES = (
    RUN_STARTED,
    THINKING,
    MESSAGE,
    TOOL_CALL,
    TOOL_RESULT,
    SOURCES,
    PROMPTS,
    VALIDITY,
    CONTEXT,
    NOTICE,
    ERROR,
    RUN_FINISHED,
)


def event(event_type: str, **payload: Any) -> dict:
    """Build one event.

    ``type`` is written first so a raw JSON dump is readable, and a payload key
    called ``type`` is refused rather than silently overwriting it.
    """
    if event_type not in ALL_TYPES:
        raise ValueError(f"Unknown research event type: {event_type!r}")
    if "type" in payload:
        raise ValueError("An event payload may not redefine 'type'.")
    return {"type": event_type, **payload}


# --------------------------------------------------------------------------- #
# SSE framing
# --------------------------------------------------------------------------- #

def sse_frame(payload: dict) -> str:
    """Encode one event as a Server-Sent Events frame.

    ``json.dumps`` is used rather than a streaming JSON encoder so a payload can
    never contain a raw newline, which would break the ``data:`` framing and
    desynchronise the client's parser.
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


#: Sent when a stream opens, so a proxy that buffers does not make the client
#: wait for the first real event before it knows the connection is live.
SSE_OPEN_FRAME = ": stream open\n\n"

#: Sent once the run is over. Tells a reconnecting client to stop.
SSE_DONE_FRAME = "event: done\ndata: {}\n\n"


def encode_stream(events: Iterable[dict]) -> Iterable[str]:
    """Yield SSE frames for a sequence of events."""
    yield SSE_OPEN_FRAME
    for payload in events:
        yield sse_frame(payload)
    yield SSE_DONE_FRAME


# --------------------------------------------------------------------------- #
# Accumulation
# --------------------------------------------------------------------------- #

class EventAccumulator:
    """Folds an event stream into the pieces the UI renders as final state.

    Streaming gives the operator live feedback, but the *result* has to be
    recoverable from the stream too (a reconnecting client, a reloaded
    conversation, or a test). Deriving it here — rather than in the client —
    keeps one definition of what "the prompts" and "the sources" of a run are,
    and means a bug in the client's reducer cannot invent a result.
    """

    def __init__(self) -> None:
        self.thinking_parts: list[str] = []
        self.message_parts: list[str] = []
        self.tool_calls: list[dict] = []
        self.sources: list[dict] = []
        self.prompts: list[dict] = []
        self.validity: dict | None = None
        self.context: dict | None = None
        self.notices: list[str] = []
        self.error: str = ""
        self.run_id: str = ""
        #: The run's *final* answer, taken from the terminal event.
        #:
        #: Deliberately not the same thing as ``message``: every turn's visible
        #: prose is streamed as a ``message`` event, including turns that were
        #: only tool calls. Reading the answer off the accumulated prose therefore
        #: produced an "answer" of `<tool_call>{…}</tool_call>` followed by the
        #: real reply — the protocol markup leaking into the stored transcript.
        self.answer: str = ""
        self._seen_urls: set[str] = set()

    def add(self, payload: dict) -> None:
        event_type = payload.get("type")
        if event_type == RUN_STARTED:
            self.run_id = payload.get("run_id", self.run_id)
        elif event_type == THINKING:
            self.thinking_parts.append(payload.get("text", ""))
        elif event_type == MESSAGE:
            self.message_parts.append(payload.get("text", ""))
        elif event_type == TOOL_CALL:
            self.tool_calls.append(
                {"name": payload.get("name", ""), "arguments": payload.get("arguments") or {}}
            )
        elif event_type == SOURCES:
            self._merge_sources(payload.get("sources") or [])
        elif event_type == PROMPTS:
            self.prompts = list(payload.get("prompts") or [])
        elif event_type == VALIDITY:
            self.validity = payload.get("validity")
        elif event_type == CONTEXT:
            # Latest wins: the report is a measurement of the conversation as it
            # stands, so the final one describes the completed run.
            self.context = {key: value for key, value in payload.items() if key != "type"}
        elif event_type == NOTICE:
            text = payload.get("text", "")
            if text and text not in self.notices:
                self.notices.append(text)
        elif event_type == ERROR:
            self.error = payload.get("text", "")
        elif event_type == RUN_FINISHED:
            answer = payload.get("answer")
            if isinstance(answer, str) and answer.strip():
                self.answer = answer.strip()

    def _merge_sources(self, incoming: list) -> None:
        """Add sources, de-duplicated by URL and in first-seen order.

        A source is often returned by more than one query; listing it twice
        would make a single page look like two independent confirmations.

        **Defensive about the shape on purpose.** The accumulator is the single
        point every streamed event passes through, so an entry that is not a dict
        — a tool that returned a bare dict instead of a list, a string, ``None`` —
        would otherwise raise here and take down a run that had already gathered
        real evidence. A malformed entry is dropped and logged: a missing source
        is a cosmetic loss, whereas ``AttributeError`` mid-stream is the failure
        where the operator loses the whole answer.

        The type is ``list`` rather than ``list[dict]`` because the caller cannot
        be trusted to have honoured the annotation, and a stricter annotation here
        would only move the crash without preventing it.
        """
        for source in incoming or []:
            if not isinstance(source, dict):
                if source:
                    logger.warning(
                        "Dropping a malformed source entry of type %s",
                        type(source).__name__,
                    )
                continue
            url = str(source.get("url") or "").strip()
            if not url or url in self._seen_urls:
                continue
            self._seen_urls.add(url)
            self.sources.append(source)

    @property
    def thinking(self) -> str:
        return "".join(self.thinking_parts).strip()

    @property
    def message(self) -> str:
        """Every visible prose fragment, concatenated.

        This is the *transcript*, not the answer: it includes the narration a
        tool-calling turn emitted before its call. Use :attr:`final_answer` when
        what is wanted is what the model concluded.
        """
        return "".join(self.message_parts).strip()

    @property
    def final_answer(self) -> str:
        """The run's answer: the terminal event's, or the transcript as a fallback."""
        return self.answer or self.message

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "thinking": self.thinking,
            "message": self.final_answer,
            "transcript": self.message,
            "tool_calls": self.tool_calls,
            "sources": self.sources,
            "prompts": self.prompts,
            "validity": self.validity,
            # The final measurement of the window, so a replayed conversation
            # shows the same indicator the live one did. Without it a reloaded
            # thread would render the bar empty, which reads as "no data" rather
            # than "this run's context position".
            "context": self.context,
            "notices": self.notices,
            "error": self.error,
        }


def summarise_tool_call(name: str, arguments: dict) -> str:
    """A one-line, human-readable description of a tool call.

    Written here rather than in the UI so the live step list and the replayed
    transcript describe the same call the same way.
    """
    if name == "web_search":
        return f"Searching the web: {arguments.get('query', '')}"
    if name == "fetch_page":
        return f"Reading: {arguments.get('url', '')}"
    if name == "market_overview":
        return f"Checking existing coverage: {arguments.get('niche', '')}"
    if name == "assess_validity":
        return "Recording the confidence assessment"
    if name == "check_prompt_similarity":
        return f"Checking {len(arguments.get('prompts') or [])} prompts for overlap"
    if name == "list_categories":
        return "Listing Adobe Stock categories"
    return f"Calling {name}"
