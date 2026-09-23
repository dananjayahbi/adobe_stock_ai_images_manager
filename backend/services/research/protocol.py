"""The tool-call protocol the research agent speaks.

Why a text protocol instead of OpenAI tool calling
--------------------------------------------------
The configured gateway does **not** support the ``tools`` / ``tool_choice``
fields. Verified on this machine (2026-09-23) against ``deepseek-v4.1-flash``:
sending a ``tools`` array returns ``finish_reason: "stop"``, ``tool_calls:
null``, and the intended call leaked into the visible ``content`` as DeepSeek's
internal markup:

.. code-block:: text

    <｜｜DSML｜｜ calls>
    <｜｜DSML｜｜ invoke name="web_search">
    <｜｜DSML｜｜ parameter name="query" string="true">…</｜｜DSML｜｜ parameter>
    </｜｜DSML｜｜ invoke>
    </｜｜DSML｜｜ calls>

That is a real capability gap, not a prompt problem, so the agent asks for a
documented text format instead and parses it. Three shapes are accepted, in
order of preference:

1. ``<tool_call>{"name": …, "arguments": {…}}</tool_call>`` — the requested
   format, and the one the system prompt teaches.
2. The same object inside a ```json fence, for models that wrap every reply.
3. DeepSeek's ``DSML`` markup, so the model's native habit still works.

The critical requirement is the opposite of most parsers: **prose that merely
mentions a tool must not be read as a call.** A reply that discusses
``web_search`` in a sentence has to come through as a final answer, or the loop
never terminates. Hence every pattern requires an explicit invocation envelope
(a ``<tool_call>`` element or a ``DSML invoke``), never a bare tool name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

#: The envelope the system prompt asks for.
TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"

_ENVELOPE = re.compile(
    rf"{re.escape(TOOL_CALL_OPEN)}(?P<body>.*?){re.escape(TOOL_CALL_CLOSE)}",
    re.S | re.I,
)

#: ```json … ``` wrapper, which several models add unconditionally.
_FENCE = re.compile(r"```(?:json)?\s*(?P<body>.*?)```", re.S | re.I)

#: DeepSeek's internal markup. The fullwidth vertical bars are written as an
#: escape so the pattern cannot be broken by an editor normalising the file.
#:
#: The separator between ``<``, ``DSML`` and the keyword is *not* stable: the
#: real output observed from this gateway contains both ``<｜｜DSML｜｜ invoke``
#: and ``< ｜｜DSML｜｜ parameter`` (a space after the angle bracket). The
#: separator is therefore matched as a run of bars-or-whitespace rather than a
#: fixed string - a strict pattern silently parsed the tool name but dropped
#: every argument.
_DSML_BAR = "\uff5c"
_DSML_SEP = rf"[\s{_DSML_BAR}]*"
_DSML_OPEN = rf"<{_DSML_SEP}DSML{_DSML_SEP}"
_DSML_CLOSE = rf"</{_DSML_SEP}DSML{_DSML_SEP}"
_DSML_INVOKE = re.compile(
    rf"{_DSML_OPEN}invoke\s+name=\"(?P<name>[^\"]+)\"\s*>(?P<body>.*?)(?={_DSML_CLOSE}invoke|$)",
    re.S | re.I,
)
_DSML_PARAM = re.compile(
    rf"{_DSML_OPEN}parameter\s+name=\"(?P<name>[^\"]+)\"[^>]*>(?P<value>.*?)(?={_DSML_CLOSE}parameter|$)",
    re.S | re.I,
)
_DSML_ANY_TAG = re.compile(rf"</?{_DSML_SEP}DSML{_DSML_SEP}[^>]*>", re.S)

#: An innermost DSML element: an open tag, a body containing **no** further DSML
#: open tag, then a close tag. Removing these repeatedly unwraps the nesting
#: (``parameter`` → ``invoke`` → ``calls``) and takes the argument *values* with
#: them. Stripping only the tags would leave a bare ``"some query"`` in the
#: transcript, which reads as if the model had said it.
_DSML_INNERMOST = re.compile(
    rf"{_DSML_OPEN}\w+\b[^>]*>(?:(?!{_DSML_OPEN}).)*?{_DSML_CLOSE}\w*\s*>",
    re.S | re.I,
)

#: How many calls one reply may contain. A model that emits dozens is looping,
#: and honouring them all would burn the whole run's budget in one turn.
MAX_CALLS_PER_REPLY = 4

#: Collapse only *intra-line* whitespace, so a reply's line structure survives
#: stripping (the prompt parser keys on line-anchored headings).
_TRAILING_SPACE = re.compile(r"[ \t]+$")
_BLANK_RUN = re.compile(r"\n{3,}")

#: A complete call envelope, JSON body included. A *truncated* envelope — an open
#: tag whose body never parses — must still be removed from the prose, or the
#: leftover markup becomes the run's answer and the prompt parser then offers it
#: as a prompt. Measured live: the model began a call, switched mid-stream to
#: DeepSeek's native DSML markup, and emitted a malformed hybrid. The reply had no
#: parseable call, so the loop treated it as the final answer and the UI presented
#: `<tool_call>{"name": …` as a prompt.
_COMPLETE_CALL = re.compile(
    rf"{re.escape(TOOL_CALL_OPEN)}.*?{re.escape(TOOL_CALL_CLOSE)}",
    re.S | re.I,
)
#: An unterminated envelope: from an open tag to the end of the reply.
_UNTERMINATED_CALL = re.compile(
    rf"{re.escape(TOOL_CALL_OPEN)}.*\Z", re.S | re.I
)


@dataclass
class ToolCall:
    """One tool invocation requested by the model."""

    name: str
    arguments: dict = field(default_factory=dict)
    #: The exact text the call was parsed from, kept so the UI can show what
    #: the model actually wrote when the arguments turn out to be wrong.
    raw: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "arguments": self.arguments}


def _strip_fences(text: str) -> str:
    """Remove a ```json fence wrapper, leaving the body."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    body = lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:]
    return "\n".join(body).strip()


def _coerce_arguments(value: object) -> dict:
    """Normalise the ``arguments`` field into a dict.

    Models variously emit a nested object, a JSON *string* containing one, or
    nothing at all. All three are accepted; anything else is treated as no
    arguments rather than raising, because a malformed call is better answered
    with "that call was invalid" than with a dead run.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return {}
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            # A bare string is accepted as the single "query"-style argument,
            # which is what a model writes when it simplifies the schema.
            return {"query": candidate}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _from_object(payload: object) -> ToolCall | None:
    """Build a call from a decoded JSON object, if it looks like one."""
    if not isinstance(payload, dict):
        return None

    name = payload.get("name") or payload.get("tool") or payload.get("function")
    if isinstance(name, dict):  # OpenAI-shaped {"function": {"name": …}}
        name = name.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    arguments = payload.get("arguments")
    if arguments is None:
        arguments = payload.get("parameters")
    if arguments is None and isinstance(payload.get("function"), dict):
        # OpenAI-shaped {"type": "function", "function": {"name": …, "arguments": …}}.
        arguments = payload["function"].get("arguments")
    if arguments is None:
        # Some models flatten the arguments into the call object itself.
        arguments = {
            key: value
            for key, value in payload.items()
            if key not in ("name", "tool", "function", "type", "id")
        }
    return ToolCall(name=name.strip(), arguments=_coerce_arguments(arguments))


def _parse_dsml(text: str) -> list[ToolCall]:
    """Recover calls written in DeepSeek's ``DSML`` markup."""
    calls: list[ToolCall] = []
    for match in _DSML_INVOKE.finditer(text):
        arguments: dict = {}
        for param in _DSML_PARAM.finditer(match.group("body")):
            raw_value = param.group("value").strip()
            # The value arrives as text; unwrap a JSON scalar so numbers and
            # arrays reach the tool as their real types.
            try:
                arguments[param.group("name")] = json.loads(raw_value)
            except json.JSONDecodeError:
                arguments[param.group("name")] = raw_value
        calls.append(
            ToolCall(name=match.group("name").strip(), arguments=arguments, raw=match.group(0))
        )
        if len(calls) >= MAX_CALLS_PER_REPLY:
            break
    return calls


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract every tool call from a model reply.

    Returns an empty list when the reply is a plain answer, which is the normal
    way the loop terminates.
    """
    if not text:
        return []

    calls: list[ToolCall] = []

    # 1. The requested envelope. The body may hold either one object or an
    #    array of them.
    for match in _ENVELOPE.finditer(text):
        body = _strip_fences(match.group("body"))
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for candidate in candidates:
            call = _from_object(candidate)
            if call is not None:
                call.raw = match.group(0)
                calls.append(call)

    # 2. A fenced JSON object with a tool-shaped body, for a model that ignored
    #    the envelope but still fenced its output.
    if not calls:
        for match in _FENCE.finditer(text):
            try:
                payload = json.loads(match.group("body"))
            except json.JSONDecodeError:
                continue
            candidates = payload if isinstance(payload, list) else [payload]
            for candidate in candidates:
                call = _from_object(candidate)
                if call is not None:
                    call.raw = match.group(0)
                    calls.append(call)

    # 3. DeepSeek's native markup.
    if not calls:
        calls = _parse_dsml(text)

    return calls[:MAX_CALLS_PER_REPLY]


def strip_tool_calls(text: str) -> str:
    """Remove tool-call markup, leaving any prose the model wrote around it.

    The research UI shows the model's own words between steps, so the raw
    protocol markup must not leak into that transcript. Fenced JSON is removed
    only when it actually decoded as a tool call — otherwise a model quoting a
    JSON example would lose its example.

    **Line structure is preserved.** An earlier version collapsed every run of
    whitespace, which silently flattened the model's whole answer onto one line —
    and the prompt parser keys on line-anchored headings, so it then recovered
    one prompt instead of the six that were there. Only intra-line whitespace and
    excessive blank lines are collapsed here.
    """
    if not text:
        return ""

    # Remove complete envelopes first, then any unterminated one (a truncated
    # call leaves an open tag with no close, so the first pattern cannot match).
    cleaned = _COMPLETE_CALL.sub(" ", text)
    cleaned = _UNTERMINATED_CALL.sub(" ", cleaned)

    # Unwrap DSML elements from the inside out, then drop any leftover tags.
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _DSML_INNERMOST.sub(" ", cleaned)
    cleaned = _DSML_ANY_TAG.sub(" ", cleaned)

    def _drop_fence(match: re.Match[str]) -> str:
        try:
            payload = json.loads(match.group("body"))
        except json.JSONDecodeError:
            return match.group(0)
        candidates = payload if isinstance(payload, list) else [payload]
        if any(_from_object(candidate) is not None for candidate in candidates):
            return " "
        return match.group(0)

    cleaned = _FENCE.sub(_drop_fence, cleaned)

    lines = [_TRAILING_SPACE.sub("", line) for line in cleaned.splitlines()]
    joined = "\n".join(lines)
    return _BLANK_RUN.sub("\n\n", joined).strip()


def format_tool_result(name: str, payload: object) -> str:
    """Render a tool's output as the message the model reads next.

    The envelope is explicit and labelled with the tool name so a model that
    called two tools in one turn can still tell the results apart.
    """
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    return f"<tool_result name=\"{name}\">\n{body}\n</tool_result>"


def format_call_error(name: str, message: str, known: list[str]) -> str:
    """Tell the model its call could not be honoured, and how to fix it.

    Fed back as a tool result rather than raised: a wrong tool name is a
    recoverable mistake the model can correct on its next turn, and the
    alternative (aborting) would waste an otherwise good run.
    """
    return (
        f"<tool_result name=\"{name or 'unknown'}\" error=\"true\">\n"
        f"That tool call could not be run: {message}\n"
        f"Available tools: {', '.join(known)}.\n"
        "Correct the call and try again, or answer with your findings.\n"
        "</tool_result>"
    )
