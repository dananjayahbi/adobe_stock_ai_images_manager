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

#: A *malformed* envelope — an open tag closed by something other than
#: ``</tool_call>``, or not closed at all — must still be removed from the prose,
#: or the leftover markup becomes the run's answer. Measured live: the model began
#: a call, switched mid-stream to DeepSeek's native DSML markup, and emitted a
#: malformed hybrid; the reply had no parseable call, so the loop treated it as the
#: final answer and the UI presented `<tool_call>{"name": …` as a prompt.
#:
#: Removal is done by :func:`_scan_open_envelopes`, which understands both the
#: proper closer and the malformed ones. This pattern is the fallback for an
#: envelope left open at the end of the reply.
_UNTERMINATED_CALL = re.compile(
    rf"{re.escape(TOOL_CALL_OPEN)}.*\Z", re.S | re.I
)

#: Where an envelope body must have ended, whether or not the model wrote a
#: ``</tool_call>``. The body is always JSON, so the first DSML tag or any
#: subsequent ``<tool_call>`` opener is past its end. Matched with
#: :func:`_scan_open_envelopes`, which prefers a real closer when there is one.
_BODY_BOUNDARY = re.compile(
    rf"</?{_DSML_SEP}DSML{_DSML_SEP}[^>]*>|{re.escape(TOOL_CALL_OPEN)}",
    re.S | re.I,
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
    """Recover calls written in DeepSeek's ``DSML`` markup.

    Two shapes reach here from the live gateway. The documented one names each
    argument directly::

        <｜｜DSML｜｜ parameter name="query" string="true">warehouse robots</｜｜DSML｜｜ parameter>

    The other wraps the whole argument object in a *single* parameter named
    ``arguments``, whose value is JSON rather than a string::

        <｜｜DSML｜｜ parameter name="arguments" string="false">{"query": "…"}</｜｜DSML｜｜ parameter>

    Captured live: without handling the second shape the tool received
    ``{"arguments": {"query": …}}``, so a correct call arrived with no ``query``
    of its own and was rejected as malformed.
    """
    calls: list[ToolCall] = []
    for match in _DSML_INVOKE.finditer(text):
        arguments: dict = {}
        for param in _DSML_PARAM.finditer(match.group("body")):
            name = param.group("name").strip()
            raw_value = param.group("value").strip()
            # The value arrives as text; unwrap a JSON scalar so numbers and
            # arrays reach the tool as their real types.
            try:
                value: object = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            if name == "arguments" and isinstance(value, dict):
                # The whole argument object arrived under one parameter.
                arguments.update(value)
                continue
            arguments[name] = value
        calls.append(
            ToolCall(name=match.group("name").strip(), arguments=arguments, raw=match.group(0))
        )
        if len(calls) >= MAX_CALLS_PER_REPLY:
            break
    return calls


def _scan_open_envelopes(text: str) -> list[tuple[int, int, str]]:
    """Find every ``<tool_call>`` opener, tolerant of a *wrong* closer.

    The gateway does not reliably emit the closer the prompt asks for. Captured
    live from ``deepseek-v4.1-flash``: the model writes a **complete and valid**
    JSON body, then closes it with DeepSeek's native DSML tags instead of
    ``</tool_call>`` —

    .. code-block:: text

        <tool_call>{"name": "market_overview", "arguments": {"niche": "…"}}</｜｜DSML｜｜ parameter>

    A regex requiring ``</tool_call>`` cannot match that, so the call was not
    parsed, the loop read the turn as a final answer, and the run ended with no
    tool executed. That is the operator's "the agent suddenly stops without
    providing the prompts", and it is a parser fault, not a model fault: the
    arguments are all there and valid.

    Returns ``(span_start, body_start, body_end, span)`` for each opener:
    ``span`` is the whole envelope as it appeared, ``span_start`` is where it
    begins in the text (so the prose can be rebuilt around it), and
    ``text[body_start:body_end]`` is the JSON to parse. The four values are
    returned rather than recomputed by the callers because ``span_start`` and
    ``body_start`` differ by the length of the opener, and conflating them made
    the strip delete the wrong slice of the reply.
    """
    spans: list[tuple[int, int, int, str]] = []
    cursor = 0
    while True:
        start = text.find(TOOL_CALL_OPEN, cursor)
        if start == -1:
            return spans
        body_start = start + len(TOOL_CALL_OPEN)
        cursor = body_start

        # Preferred: a proper closer.
        close = text.find(TOOL_CALL_CLOSE, body_start)
        # The JSON body always begins with `{` or `[`. Any of these markers means
        # the body has ended, whether or not a `</tool_call>` followed.
        boundary = _BODY_BOUNDARY.search(text, body_start)
        if close != -1 and (boundary is None or close <= boundary.start()):
            end = close + len(TOOL_CALL_CLOSE)
            spans.append((start, body_start, close, text[start:end]))
            cursor = end
            continue
        if boundary is not None:
            spans.append(
                (start, body_start, boundary.start(), text[start : boundary.start()])
            )
            cursor = boundary.start()
            continue
        # Nothing but the body, truncated at the end of the reply.
        spans.append((start, body_start, len(text), text[start:]))
        return spans


def _balanced_json(text: str, start: int) -> str | None:
    """The balanced ``{…}`` or ``[…]`` starting at ``start``, if there is one.

    Brace counting rather than a regex, so a brace inside a JSON *string* (a
    query containing ``"`` or ``{``) cannot end the object early.
    """
    if start >= len(text) or text[start] not in "{[":
        return None
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _calls_from_body(body: str) -> list[ToolCall]:
    """Parse the JSON object(s) in an envelope body into calls."""
    candidates: list[ToolCall] = []
    trimmed = _strip_fences(body).strip()
    if not trimmed:
        return candidates

    decoded: object | None = None
    try:
        decoded = json.loads(trimmed)
    except json.JSONDecodeError:
        # The body may be followed by trailing markup the boundary scan could not
        # see, so fall back to the balanced object at the front of it.
        balanced = _balanced_json(trimmed, trimmed.find("{") if "{" in trimmed else 0)
        if balanced:
            try:
                decoded = json.loads(balanced)
            except json.JSONDecodeError:
                return candidates
        else:
            return candidates

    items = decoded if isinstance(decoded, list) else [decoded]
    for item in items:
        call = _from_object(item)
        if call is not None:
            candidates.append(call)
    return candidates


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract every tool call from a model reply.

    Returns an empty list when the reply is a plain answer, which is the normal
    way the loop terminates.
    """
    if not text:
        return []

    calls: list[ToolCall] = []

    # 1. The requested envelope, tolerant of how the model closed it. The body may
    #    hold either one object or an array of them.
    for _span_start, body_start, body_end, span in _scan_open_envelopes(text):
        for call in _calls_from_body(text[body_start:body_end]):
            call.raw = span
            calls.append(call)
    calls = calls[:MAX_CALLS_PER_REPLY]

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

    # Remove every envelope, using the same tolerant scan the parser uses. A
    # regex keyed on `</tool_call>` alone leaves the *malformed* envelopes in the
    # prose — and those are the ones that matter most, because they are exactly
    # the turns that failed to parse as calls. Captured live: the model closed a
    # JSON body with `</｜｜DSML｜｜ parameter>`, and the leftover tags were
    # streamed to the operator as the agent's own words.
    #
    # Rebuilt by offset rather than by `str.replace`: the same envelope text can
    # legitimately appear twice (a model repeating itself, or a JSON *string* that
    # contains the markup), and `replace` would then delete the wrong occurrence —
    # or, if the text no longer matched, silently delete nothing.
    cleaned = text
    for span_start, _body_start, _body_end, span in reversed(_scan_open_envelopes(text)):
        end = span_start + len(span)
        if cleaned[span_start:end] == span:
            cleaned = cleaned[:span_start] + " " + cleaned[end:]
    # Anything still open (a truncated call at the very end of the reply).
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


def format_tool_result(name: str, payload: object, *, error: bool = False) -> str:
    """Render a tool's output as the message the model reads next.

    The envelope is explicit and labelled with the tool name so a model that
    called two tools in one turn can still tell the results apart.

    ``error=True`` marks a *failure* rather than an empty success. The distinction
    matters: a result envelope that looks ordinary invites the model to treat "no
    data" as "nothing exists", which is exactly the wrong conclusion to draw from
    a call that was rejected before it ran.
    """
    if isinstance(payload, str):
        body = payload
    else:
        body = json.dumps(payload, ensure_ascii=False, indent=2)
    attribute = ' error="true"' if error else ""
    return f"<tool_result name=\"{name}\"{attribute}>\n{body}\n</tool_result>"


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
