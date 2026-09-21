"""Turn a model's context window into concrete request limits.

The Settings modal lets the operator declare how large a context window the
configured model has. That number is only useful if it changes what we send, so
this module converts it into two decisions:

* **How large an image may be.** A vision request is billed in 512px tiles, so a
  full-resolution photo can consume a whole small window on its own. The cap is
  the largest standard size whose tile cost fits in a share of the window.
* **How many tokens the reply may use.** Everything left after the image and the
  prompt is available for the JSON answer, clamped so a huge window does not
  invite a runaway generation.

The tile model is OpenAI's published vision pricing scheme; it is a good
approximation for any tile-based vision encoder and errs slightly high, which is
the safe direction when the goal is "do not overflow the window".
"""

from __future__ import annotations

import math

#: Vision encoders split an image into fixed-size tiles for accounting.
TILE_PX = 512
#: Per-request overhead and per-tile cost, in tokens (OpenAI's figures).
BASE_TOKENS = 85
TOKENS_PER_TILE = 170
#: An image is first scaled down so its long edge is at most this.
MAX_SIDE = 2048
#: ...and then so its short edge is at most this.
SHORT_SIDE = 768

#: Image caps, largest first. The cap may be *lowered* toward the next entry
#: when the context window cannot afford it; it is never raised above the
#: operator's ``LLM_IMAGE_MAX_DIM`` preference.
IMAGE_CAPS: tuple[int, ...] = (2048, 1536, 1024, 768, 512)

#: Share of the context window an image is allowed to occupy.
IMAGE_BUDGET_SHARE = 0.5
#: Rough token count of the instruction text, reserved before the image.
PROMPT_RESERVE_TOKENS = 512

#: Share of the context window the reply may use.
#:
#: This matters because of **reasoning models**. A model like
#: ``deepseek-v4.1-flash`` streams its chain of thought into a separate
#: ``reasoning_content`` field *before* emitting ``content``, and those tokens
#: are billed against ``max_tokens``. Measured on this repo's metadata prompt:
#: one pass spent 2,503 reasoning tokens to produce an 867-character JSON
#: answer, and another spent 8,054. A budget sized only for the visible answer
#: is therefore truncated mid-thought, the reply comes back with
#: ``finish_reason: "length"`` and an **empty** ``content``, and the record
#: looks like it "generated nothing" even though the endpoint is healthy.
COMPLETION_SHARE = 0.25

#: Multiplier applied to the budget on each retry. A truncated request is the
#: only signal that a reasoning model needs more room, so the growth has to be
#: decisive: measured thinking lengths varied 2.5k-8k tokens for the *same*
#: prompt, which a gentle increase would not clear.
RETRY_BUDGET_FACTOR = 4

#: Smallest completion budget worth asking for; below this a truncated reply is
#: more likely than a usable one, so the budget simply stops shrinking.
COMPLETION_BUDGET_FLOOR = 256

#: Characters per token. Crude, but only used to keep a safety margin honest.
_CHARS_PER_TOKEN = 4

#: Rough output-token ceiling per model family, used to size the *first* request.
#:
#: This is what makes the budget adaptive rather than a fixed guess: a model with
#: a large declared ceiling is given room to think up front, while one with a
#: small ceiling is not over-asked. Matched on a substring of the model id, so a
#: dated or vendor-prefixed variant still resolves.
_MODEL_OUTPUT_CEILINGS: tuple[tuple[str, int], ...] = (
    ("deepseek", 32_768),
    ("o1", 32_768),
    ("o3", 32_768),
    ("o4", 32_768),
    ("qwq", 32_768),
    ("reason", 32_768),
    ("thinking", 32_768),
    ("claude", 32_768),
    ("gpt-5", 32_768),
    ("gemini", 32_768),
    ("grok", 32_768),
    ("qwen", 32_768),
    ("llama", 16_384),
    ("mistral", 16_384),
    ("mixtral", 16_384),
)

#: Ceiling used when the model is not recognised. Deliberately generous:
#: a non-reasoning model stops on its own (``finish_reason: "stop"``) and never
#: spends the extra budget, so over-asking is free while under-asking silently
#: breaks reasoning models.
DEFAULT_OUTPUT_CEILING = 16_384

#: Absolute ceiling on any budget, whatever the model claims.
ABSOLUTE_MAX_COMPLETION_TOKENS = 65_536


def model_output_ceiling(model: str) -> int:
    """A conservative output-token ceiling for a model id.

    Recognises reasoning families by name; everything else gets
    :data:`DEFAULT_OUTPUT_CEILING`. The result is only used to size a request -
    never to reject one - so a wrong guess costs a little wasted headroom rather
    than a failure.
    """
    lowered = (model or "").lower()
    for needle, ceiling in _MODEL_OUTPUT_CEILINGS:
        if needle in lowered:
            return ceiling
    return DEFAULT_OUTPUT_CEILING


def estimate_image_tokens(width: int, height: int) -> int:
    """Estimate the vision token cost of an image of this size.

    Returns the bare per-request overhead for a degenerate size, so callers
    never have to special-case a missing dimension.
    """
    if width <= 0 or height <= 0:
        return BASE_TOKENS

    scale = min(1.0, MAX_SIDE / max(width, height))
    scaled_w, scaled_h = width * scale, height * scale

    shortest = min(scaled_w, scaled_h)
    if shortest > SHORT_SIDE:
        shrink = SHORT_SIDE / shortest
        scaled_w, scaled_h = scaled_w * shrink, scaled_h * shrink

    tiles = math.ceil(scaled_w / TILE_PX) * math.ceil(scaled_h / TILE_PX)
    return BASE_TOKENS + TOKENS_PER_TILE * tiles


def _largest_cap_within(budget: int) -> int:
    """Largest standard image cap whose tile cost fits ``budget`` tokens.

    The smallest cap is returned when even that overflows, so the result is
    always one of :data:`IMAGE_CAPS`.
    """
    for cap in IMAGE_CAPS:
        if estimate_image_tokens(cap, cap) <= budget:
            return cap
    return IMAGE_CAPS[-1]


def image_dimension_cap(
    context_window: int, share: float = IMAGE_BUDGET_SHARE
) -> int:
    """Largest standard image cap whose tile cost fits the window's image share."""
    return _largest_cap_within(max(BASE_TOKENS, int(context_window * share)))


def resolve_image_max_dim(context_window: int, configured: int) -> int:
    """Reconcile the operator's quality preference with the model's window.

    ``configured`` (``LLM_IMAGE_MAX_DIM``) expresses how much detail we would
    *like* to send; the window expresses what we *can* send. The smaller wins,
    so a generous window can never raise the cap above what was asked for.

    In practice the window only bites at degenerate values. A vision encoder
    rescales to a 768px short side before accounting, so any image at or above
    that costs ~765 tokens regardless of its original size - comfortably inside
    the image share of even the smallest *supported* window (4096 tokens). The
    window therefore governs the reply budget, and this cap is a safety net for
    a window configured below the supported floor via the environment.
    """
    try:
        preferred = int(configured)
    except (TypeError, ValueError):
        preferred = 1024
    if preferred <= 0:
        preferred = 1024
    return max(256, min(preferred, image_dimension_cap(context_window)))


def completion_token_budget(
    context_window: int,
    *,
    image_tokens: int = 0,
    prompt: str = "",
    attempt: int = 1,
    model: str = "",
) -> int:
    """Tokens the model may spend on its reply without overrunning the window.

    Args:
        context_window: The model's declared window.
        image_tokens: Estimated cost of the attached image.
        prompt: The instruction text, for a rough token estimate.
        attempt: 1-based retry index. Each retry asks for a multiple more room,
            because the only way to discover a reasoning model's thinking length
            is to be truncated by it once.
        model: The model id, used to pick a sensible output ceiling so the first
            attempt is already large enough for a known reasoning family.

    Returns:
        A token budget clamped to the room actually available in the window.
    """
    prompt_tokens = math.ceil(len(prompt) / _CHARS_PER_TOKEN) if prompt else 0
    available = context_window - image_tokens - prompt_tokens - PROMPT_RESERVE_TOKENS
    if available < COMPLETION_BUDGET_FLOOR:
        return COMPLETION_BUDGET_FLOOR

    # Size from the smaller of what the model family can emit and what the
    # window's reply share allows, so a 200k-window model is not asked for
    # 50k tokens of thinking on a task that needs 2k.
    target = min(model_output_ceiling(model), int(context_window * COMPLETION_SHARE))

    if attempt <= 1:
        desired = target
    else:
        desired = target * (RETRY_BUDGET_FACTOR ** (attempt - 1))

    desired = min(desired, ABSOLUTE_MAX_COMPLETION_TOKENS)
    # Never exceed the room left in the window: the provider would reject the
    # request outright, which is a worse failure than a shorter answer.
    return max(COMPLETION_BUDGET_FLOOR, min(desired, available))


def is_truncated(envelope: dict) -> bool:
    """True when the model ran out of budget before finishing its answer.

    A truncated response is the signature of a reasoning model whose thinking
    exceeded ``max_tokens``: ``finish_reason`` is ``"length"`` and the visible
    ``content`` is empty. Distinguishing this from a genuinely empty reply is
    what lets the caller retry with more room instead of giving up.
    """
    choices = envelope.get("choices") or []
    if not choices:
        return False
    return choices[0].get("finish_reason") == "length"


def reasoning_tokens(envelope: dict) -> int:
    """Reasoning tokens the provider reported for a response, or 0.

    Providers expose this in different places, so both are checked; it is used
    only for logging and to size a retry, never to gate behaviour.
    """
    usage = envelope.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    reported = details.get("reasoning_tokens")
    if isinstance(reported, int):
        return reported
    message = ((envelope.get("choices") or [{}])[0].get("message")) or {}
    return len(message.get("reasoning_content") or "") // _CHARS_PER_TOKEN
