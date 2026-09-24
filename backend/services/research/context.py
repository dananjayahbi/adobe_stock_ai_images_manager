"""Keeping a long research conversation inside the model's context window.

A research thread is not one request: every tool call adds a turn to the
conversation, and a tool result can be thousands of characters of page text. A
multi-source investigation therefore grows without bound, and the failure is
**silent and destructive** — the provider either rejects the request or truncates
it from the front, so the model loses the system prompt that tells it how to
answer and the operator sees a run that "stopped for no reason".

Three jobs live here:

* **Measure.** :func:`estimate_tokens` and :func:`window_report` turn the message
  list into a token figure and a percentage of the declared window, so the UI can
  show a live indicator instead of the operator discovering the limit by hitting it.
* **Fold.** :func:`summarise_history` replaces the *older* part of a conversation
  with a compact digest, keeping the most recent turns verbatim. The model keeps
  what it was just told and what it just found; it loses the blow-by-blow of the
  opening exchanges, which the digest preserves the substance of.
* **Report honestly.** :func:`window_report` reports what was folded and what was
  lost. A summary that quietly dropped a finding would be worse than no summary,
  because the model would then reason confidently from a hole in its evidence.

Token counts are *estimates*. No tokenizer is available for every gateway model,
and an estimate that is explicit about being one is more useful than a false
precision — the indicator exists to show a trend and to trigger folding before the
limit is reached, not to predict a bill.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from services.llm_client import LLMError, stream_chat

logger = logging.getLogger(__name__)

#: Characters per token. Crude, and deliberately the same figure
#: :mod:`services.llm_budget` uses so the two cannot disagree about a prompt's
#: size. Real ratios run ~3.5-4.5 for English prose; this sits in the middle and
#: slightly over-counts code and JSON, which is the safe direction.
CHARS_PER_TOKEN = 4

#: Per-message overhead (role, separators). Small, but a long tool-call
#: conversation has many messages, so ignoring it under-counts by hundreds.
MESSAGE_OVERHEAD_TOKENS = 4

#: Share of the window at which the history is folded. Below 1.0 because the
#: reply needs room too: a conversation sized to exactly fill the window leaves
#: the model nowhere to write its answer.
COMPACT_AT_SHARE = 0.70

#: Share of the window at which the indicator warns the operator.
WARN_AT_SHARE = 0.85

#: Most recent turns kept verbatim when folding. The operator's own instruction
#: calls for "the last 5 API requests" to survive intact: those are what the
#: follow-up questions refer to ("that second idea", "yes, continue").
KEEP_RECENT_TURNS = 5

#: Share of the window held back for the digest that replaces the folded turns
#: and for the model's own reply. Folding down to *exactly* the threshold is not
#: enough: the digest is inserted into the same request, so a conversation folded
#: to the threshold plus a digest still overflows. Without this reserve the
#: measured result sat at 100% of the window, which is the failure the mechanism
#: exists to prevent.
DIGEST_RESERVE_SHARE = 0.25

#: How many characters of a single message are shown to the summariser. A tool
#: result can be the whole text of a web page; folding several of those into one
#: request would itself overflow the window, which is the problem being solved.
SUMMARISER_INPUT_CHARS = 24_000

#: Marker appended to a turn that had to be cut for the summariser.
_OMISSION_MARKER = "\n[… rest of this turn omitted …]"

#: Smallest excerpt worth showing for one turn. Below this a turn is not
#: identifiable, so a digest built from several of them could not tell the
#: operator's request from a tool result.
MIN_TURN_EXCERPT_CHARS = 300

#: Longest digest the summariser may return, as a safety net. The prompt asks for
#: far less; this stops a runaway generation from re-creating the problem.
MAX_SUMMARY_CHARS = 6_000

#: Characters kept per message when the summariser is unavailable. A local
#: truncation is a worse digest than a model's, but it is far better than
#: dropping the turn — and it always terminates.
FALLBACK_EXCERPT_CHARS = 600

#: Instruction for the folding call. Deliberately explicit about preserving
#: *facts the agent needs to answer later* rather than narrative, because a
#: summary that reads well but omits the catalogue figures is useless here.
SUMMARY_INSTRUCTION = (
    "You are compacting an in-progress research conversation so it fits in a "
    "smaller context window. Write a dense factual digest of everything below.\n\n"
    "PRESERVE, with their exact numbers and names:\n"
    "- every niche, idea or concept that was under discussion;\n"
    "- every figure a tool returned (catalogue counts, result counts, marketplace "
    "names, URLs) and which tool produced it;\n"
    "- every conclusion reached, every decision the operator made, and anything "
    "the operator asked for;\n"
    "- every confidence score recorded and the reasoning behind it;\n"
    "- which searches failed or were blocked, so that is not mistaken for an "
    "empty market.\n\n"
    "DISCARD: pleasantries, restated plans, and the agent's step-by-step "
    "narration of what it was about to do.\n\n"
    "Write plain prose in at most 300 words. Do not invent anything that is not "
    "in the text. Do not add advice or a conclusion of your own."
)

#: Prefix on the digest when it is injected back into the conversation. States
#: plainly that this is a summary, so the model does not cite it as a source.
SUMMARY_PREFIX = (
    "[CONVERSATION SUMMARY — the earlier part of this conversation was compacted "
    "to fit the context window. Treat the following as your own record of what "
    "happened. Do not cite it as an external source, and do not claim to have "
    "read pages it does not mention.]"
)


@dataclass
class WindowReport:
    """A measurement of how full the context window is.

    ``used_tokens`` counts the conversation as it would be *sent*; the reply and
    the system prompt are separate line items so the bar's total matches what the
    provider will actually see.
    """

    used_tokens: int
    window_tokens: int
    system_tokens: int = 0
    history_tokens: int = 0
    message_tokens: int = 0
    turns: int = 0
    #: Set when this report was produced by folding a longer history.
    compacted: bool = False
    #: How many turns were replaced by the digest.
    folded_turns: int = 0
    #: True when folding was needed but could not be performed.
    degraded: bool = False
    note: str = ""

    @property
    def used_share(self) -> float:
        """Fraction of the window in use, clamped to 0-1 for display."""
        if self.window_tokens <= 0:
            return 0.0
        return max(0.0, min(1.0, self.used_tokens / self.window_tokens))

    @property
    def percent(self) -> float:
        """The share as a percentage, rounded for display."""
        return round(self.used_share * 100, 1)

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.window_tokens - self.used_tokens)

    @property
    def level(self) -> str:
        """``ok`` / ``warn`` / ``critical``, for the indicator's colour.

        Three levels rather than a continuous gradient: the operator needs to
        know whether to start a new thread, and a colour that shifts by degrees
        answers that question less clearly than a threshold does.
        """
        if self.used_share >= 0.95:
            return "critical"
        if self.used_share >= WARN_AT_SHARE:
            return "warn"
        return "ok"

    def to_dict(self) -> dict:
        return {
            "used_tokens": self.used_tokens,
            "window_tokens": self.window_tokens,
            "system_tokens": self.system_tokens,
            "history_tokens": self.history_tokens,
            "message_tokens": self.message_tokens,
            "remaining_tokens": self.remaining_tokens,
            "percent": self.percent,
            "level": self.level,
            "turns": self.turns,
            "compacted": self.compacted,
            "folded_turns": self.folded_turns,
            "degraded": self.degraded,
            "note": self.note,
        }


def estimate_tokens(text: str) -> int:
    """Estimated token count of a string.

    Returns 0 for empty input so callers can sum without a special case.
    """
    if not text:
        return 0
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


def estimate_messages(messages: list[dict]) -> int:
    """Estimated token count of a whole message list, overhead included."""
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            # A multimodal part list: count the text parts, and allow a fixed
            # cost for an image rather than guessing at its tiles.
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += estimate_tokens(str(part.get("text") or ""))
                else:
                    total += 256
        else:
            total += estimate_tokens(str(content or ""))
        total += MESSAGE_OVERHEAD_TOKENS
    return total


def compact_threshold(window_tokens: int) -> int:
    """The token count at which the history should be folded."""
    if window_tokens <= 0:
        return 0
    return int(window_tokens * COMPACT_AT_SHARE)


def should_compact(messages: list[dict], window_tokens: int) -> bool:
    """Whether this conversation is large enough to need folding."""
    if window_tokens <= 0:
        return False
    return estimate_messages(messages) >= compact_threshold(window_tokens)


def fold_budget(window_tokens: int) -> int:
    """Tokens the *retained* part of a folded conversation may occupy.

    Lower than :func:`compact_threshold` because the digest goes into the same
    request as the turns that are kept: folding to the threshold leaves no room
    for the thing that replaced what was folded, and the measurement then sits at
    100% of the window — a request the provider truncates from the front, losing
    the system prompt.

    A floor keeps this from collapsing to nothing on a tiny window; when even that
    cannot be met the retention shrinks to the newest turn (see
    :func:`_keep_count`).
    """
    if window_tokens <= 0:
        return 0
    return max(MIN_TURN_EXCERPT_CHARS * 2, int(window_tokens * (COMPACT_AT_SHARE - DIGEST_RESERVE_SHARE)))


def _keep_count_within(retained: list[dict], budget: int, target: int) -> int:
    """How many of ``retained`` (counted from the newest) fit ``budget``.

    Always keeps at least one turn: a digest with no verbatim anchor cannot be
    acted on, so a fold that keeps nothing recent is worse than an aggressive one.
    """
    count = min(max(1, target), len(retained))
    while count > 1 and estimate_messages(retained[-count:]) > budget:
        count -= 1
    return count


def _keep_count(retained: list[dict], window_tokens: int, keep_recent: int) -> int:
    """How many turns to keep verbatim when fitting a *history* into the window.

    ``keep_recent`` is the *target*, not a guarantee. A tool result can be the
    whole text of a web page, so five of them can exceed a small window on their
    own; keeping them all would leave the conversation exactly as full as before
    folding, and the run would die on its next turn. So the target is walked down
    from the newest turn until the kept turns fit the reserve.
    """
    return _keep_count_within(retained, fold_budget(window_tokens), keep_recent)


def _as_history(turns: list[dict]) -> list[dict]:
    """Normalise stored turns into the ``{role, content}`` shape the model takes."""
    history: list[dict] = []
    for turn in turns or []:
        role = turn.get("role")
        content = str(turn.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            history.append({"role": role, "content": content})
    return history


def _fallback_digest(messages: list[dict]) -> str:
    """A local, truncated digest used when the summariser cannot be reached.

    Deterministic and always terminates, which is the point: folding must not be
    able to fail, or a full window becomes unrecoverable.
    """
    lines: list[str] = []
    for message in messages:
        role = "Operator" if message.get("role") == "user" else "Agent"
        text = " ".join(str(message.get("content") or "").split())
        if not text:
            continue
        if len(text) > FALLBACK_EXCERPT_CHARS:
            text = text[:FALLBACK_EXCERPT_CHARS].rstrip() + "…"
        lines.append(f"- {role}: {text}")
    return "\n".join(lines)[:MAX_SUMMARY_CHARS]


def _summariser_input(messages: list[dict]) -> str:
    """Render the turns to fold into the summariser's prompt, bounded in size.

    Bounded **per message** rather than by cutting the whole transcript. A
    character-based head/tail split looks reasonable but loses information
    badly: it keeps the start of the first turn and the end of the last, so a
    turn whose *label* sits just past the cut ("LATEST-FINDING …") disappears
    entirely and the digest cannot see that it existed.

    Truncating each message keeps the opening of every turn — which is where the
    operator's question, the tool's name and a result's headline figures live —
    and spends the remaining budget evenly.
    """
    if not messages:
        return ""

    # Budget the framing as well as the content: each block costs a role heading
    # plus, when truncated, an omission marker. Ignoring that overhead made the
    # rendered input overshoot its own cap once a conversation had many turns —
    # which is exactly the case this function exists for.
    overhead = len(messages) * (len("### OPERATOR\n") + len(_OMISSION_MARKER))
    budget = max(0, SUMMARISER_INPUT_CHARS - overhead)
    # A floor keeps each turn legible (a 20-character fragment says nothing), at
    # the cost of a slight overshoot on a very long transcript — an acceptable
    # trade, because the alternative is a digest that cannot tell the turns apart.
    per_message = max(MIN_TURN_EXCERPT_CHARS, budget // len(messages))

    blocks: list[str] = []
    for message in messages:
        role = "OPERATOR" if message.get("role") == "user" else "AGENT"
        text = str(message.get("content") or "").strip()
        if len(text) > per_message:
            text = text[:per_message].rstrip() + _OMISSION_MARKER
        blocks.append(f"### {role}\n{text}")
    return "\n\n".join(blocks)


def summarise_turns(
    messages: list[dict],
    *,
    window_tokens: int = 0,
    temperature: float = 0.2,
) -> tuple[str, str]:
    """Fold a list of turns into a digest.

    Returns ``(digest, note)``. ``note`` is empty on success and otherwise says
    why the local fallback was used, so a degraded summary is never presented as
    a model-written one.

    A failed summariser call never raises: folding is what keeps a long run
    alive, so it has to succeed in some form.
    """
    if not messages:
        return "", ""

    prompt = (
        f"{SUMMARY_INSTRUCTION}\n\n"
        f"--- TRANSCRIPT TO COMPACT ---\n{_summariser_input(messages)}"
    )
    collected: list[str] = []
    try:
        for kind, text in stream_chat(
            [{"role": "user", "content": prompt}], temperature=temperature
        ):
            if kind == "content":
                collected.append(text)
    except LLMError as exc:
        logger.warning("Context summarisation failed: %s", exc)
        return _fallback_digest(messages), (
            "The conversation was compacted with a local excerpt rather than a "
            f"model-written summary ({exc}). Some detail from earlier turns may "
            "be missing."
        )
    except Exception as exc:  # noqa: BLE001 - folding must never break a run
        logger.exception("Context summarisation crashed")
        return _fallback_digest(messages), (
            "The conversation was compacted with a local excerpt rather than a "
            f"model-written summary ({type(exc).__name__}). Some detail from "
            "earlier turns may be missing."
        )

    digest = " ".join("".join(collected).split()).strip()
    if not digest:
        return _fallback_digest(messages), (
            "The summariser returned nothing, so a local excerpt was used "
            "instead. Some detail from earlier turns may be missing."
        )
    return digest[:MAX_SUMMARY_CHARS], ""


@dataclass
class FoldedHistory:
    """The result of fitting a history into a window."""

    messages: list[dict] = field(default_factory=list)
    #: The digest that replaced the older turns, empty when nothing was folded.
    summary: str = ""
    folded_turns: int = 0
    note: str = ""
    degraded: bool = False


def summarise_history(
    turns: list[dict],
    *,
    window_tokens: int,
    keep_recent: int = KEEP_RECENT_TURNS,
    temperature: float = 0.2,
) -> FoldedHistory:
    """Fit a stored conversation into the window, folding the oldest turns.

    The newest ``keep_recent`` turns are kept **verbatim**: they are what a
    follow-up refers to, and a summary of "the idea you just gave me" is exactly
    the thing that makes a follow-up ambiguous.

    Returns the history unchanged when it already fits, so a short conversation
    costs nothing and produces no spurious summary event.
    """
    history = _as_history(turns)
    if not history:
        return FoldedHistory(messages=[])

    # The new turn is not in `history` yet, so leave room for it and the reply.
    budget = compact_threshold(window_tokens) if window_tokens > 0 else 0
    if budget <= 0 or estimate_messages(history) <= budget:
        return FoldedHistory(messages=history)

    keep = max(0, keep_recent)
    if keep:
        # Trim the target down when the newest turns alone would fill the window:
        # five whole web pages is not a "recent" tail, it is the same problem.
        keep = _keep_count(history, window_tokens, keep)
    older = history[:-keep] if keep else history
    recent = history[-keep:] if keep else []
    if not older:
        # Everything is "recent" but still too large. Fold all but the final
        # exchange rather than sending an overflowing request: the alternative is
        # a hard failure at the provider.
        older = history[:-2]
        recent = history[-2:]
    if not older:
        return FoldedHistory(
            messages=history,
            note=(
                "This conversation is too large for the model's context window "
                "and could not be compacted. Start a new thread, or raise the "
                "context window in Settings."
            ),
            degraded=True,
        )

    digest, note = summarise_turns(older, window_tokens=window_tokens, temperature=temperature)
    if not digest:
        return FoldedHistory(
            messages=history,
            note=(
                "This conversation is too large for the model's context window "
                "and could not be compacted. Start a new thread, or raise the "
                "context window in Settings."
            ),
            degraded=True,
        )

    folded = [{"role": "user", "content": f"{SUMMARY_PREFIX}\n\n{digest}"}]
    return FoldedHistory(
        messages=[*folded, *recent],
        summary=digest,
        folded_turns=len(older),
        note=note,
        degraded=bool(note),
    )


def compact_live_messages(
    messages: list[dict],
    *,
    window_tokens: int,
    keep_recent: int = KEEP_RECENT_TURNS,
    temperature: float = 0.2,
) -> tuple[list[dict], FoldedHistory]:
    """Fold a *running* conversation when the tool results have filled the window.

    :func:`summarise_history` fits the history that was already stored before the
    run began. This is the other half: a single turn can add many large tool
    results, so a run that started comfortably inside the window can still push
    itself out of it. Measured live with a small window: the final measurement was
    **100% of the window**, and the request would have been truncated at the
    provider on the next turn — losing the system prompt.

    The system prompt and the operator's newest message are never folded: the first
    carries the instructions, and the second is what the run is answering. Only the
    middle — tool calls, tool results and the model's own narration — is eligible.

    Returns ``(messages, folded)`` where ``folded.folded_turns`` is 0 when nothing
    needed to change.
    """
    if window_tokens <= 0 or len(messages) < 3:
        return messages, FoldedHistory(messages=messages)

    system = messages[0]
    # The last user message is the current question, so it is pinned as well.
    tail_start = len(messages)
    for index in range(len(messages) - 1, 0, -1):
        if messages[index].get("role") == "user":
            tail_start = index
            break

    middle = messages[1:tail_start]
    tail = messages[tail_start:]
    if len(middle) <= 1:
        # Nothing between the system prompt and the current question to fold.
        return messages, FoldedHistory(messages=messages)

    # Only fold when the *whole* conversation is over the threshold; measuring the
    # middle alone would compact a run that still has room.
    if estimate_messages(messages) < compact_threshold(window_tokens):
        return messages, FoldedHistory(messages=messages)

    # The reserve covers the digest *and* the pinned system prompt, which cannot
    # be folded away and is the largest single message in a research run.
    budget = max(1, fold_budget(window_tokens) - estimate_messages([system]))
    keep = _keep_count_within(middle, budget, keep_recent)
    older = middle[:-keep]
    recent = middle[-keep:]
    if not older:
        return messages, FoldedHistory(messages=messages)

    digest, note = summarise_turns(
        older, window_tokens=window_tokens, temperature=temperature
    )
    if not digest:
        return messages, FoldedHistory(
            messages=messages,
            note=(
                "This turn grew past the model's context window and could not be "
                "compacted. Start a new thread, or raise the context window in "
                "Settings."
            ),
            degraded=True,
        )

    folded = FoldedHistory(
        messages=[system, *recent, *tail],
        summary=digest,
        folded_turns=len(older),
        note=note,
        degraded=bool(note),
    )
    # The digest replaces the folded turns as a single user turn, so it is spliced
    # in where they were rather than appended at the end.
    return [system, {"role": "user", "content": f"{SUMMARY_PREFIX}\n\n{digest}"}, *recent, *tail], folded


def window_report(
    messages: list[dict],
    window_tokens: int,
    *,
    folded: FoldedHistory | None = None,
) -> WindowReport:
    """Measure a conversation against the window.

    ``system_tokens`` is reported separately because it is the part the operator
    never sees and cannot trim — knowing that the instructions alone cost a
    tenth of the window explains why a short-looking thread is already full.
    """
    system_tokens = 0
    rest = messages
    if messages and messages[0].get("role") == "system":
        system_tokens = estimate_tokens(str(messages[0].get("content") or ""))
        rest = messages[1:]

    history_tokens = sum(
        estimate_messages([message]) for message in rest if message.get("role") != "user"
    )
    message_tokens = sum(
        estimate_messages([message]) for message in rest if message.get("role") == "user"
    )
    used = system_tokens + history_tokens + message_tokens

    report = WindowReport(
        used_tokens=used,
        window_tokens=window_tokens,
        system_tokens=system_tokens,
        history_tokens=history_tokens,
        message_tokens=message_tokens,
        turns=len(rest),
    )
    if folded is not None:
        report.compacted = folded.folded_turns > 0
        report.folded_turns = folded.folded_turns
        report.degraded = folded.degraded
        report.note = folded.note
    return report
