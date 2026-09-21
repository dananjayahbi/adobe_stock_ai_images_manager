"""OpenAI-compatible chat client for the local multi-provider LLM gateway.

The gateway (see Local-Multi-Provider-LLM-Router) exposes
``POST {base_url}/chat/completions`` and routes by the *virtual model name*
configured for a pool, e.g. ``OpenRouter-Free-Endpoint``.

Endpoint, model, key, and context window are resolved per request through
:mod:`services.app_settings`, so the operator can point the app at any
OpenAI-compatible vision endpoint from the Settings modal without a restart.

Only the standard library is used so the backend gains no extra dependency.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from services import app_settings, llm_budget

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the gateway cannot be reached or returns an unusable reply."""


class LLMTruncatedError(LLMError):
    """Raised when the model ran out of token budget before answering.

    Distinct from a plain :class:`LLMError` because it is *retryable with more
    room* rather than a configuration fault. It is the signature of a reasoning
    model whose chain of thought consumed the whole ``max_tokens`` allowance, so
    the visible ``content`` came back empty.
    """


def _encode_image(path: Path, max_dim: int) -> str:
    """Read an image, downscale it, and return a base64 JPEG data URL.

    Downscaling keeps vision requests small; full-resolution AI images would
    otherwise push multi-megabyte payloads through the gateway and can consume
    a small context window on their own.
    """
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max_dim > 0 and max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _strip_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that models sometimes add."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    body = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
    return "\n".join(body).strip()


#: Instruction for the Settings-modal connection probe. Short, and answerable
#: from the tiny probe image so the model cannot stall on a hard question.
_PROBE_PROMPT = (
    "This is a connection test. Reply with ONLY this JSON object and nothing "
    'else: {"ok": true}'
)


def _probe_image_data_url(size: int = 32) -> str:
    """A negligible generated image, as a base64 JPEG data URL.

    Generated rather than read from disk so the probe works before any image has
    been uploaded, and small enough that it adds almost nothing to the request.
    """
    colour = Image.new("RGB", (size, size), (47, 185, 214))
    buf = io.BytesIO()
    colour.save(buf, format="JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _extract_json(text: str) -> dict:
    """Parse a JSON object from a model reply, tolerating surrounding prose.

    Tries, in order: the raw text, fenced-block stripping, then the outermost
    ``{ ... }`` span. Raises json.JSONDecodeError if none of these yield an
    object.
    """
    candidates = [text, _strip_fences(text)]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    last_error: json.JSONDecodeError | None = None
    for candidate in candidates:
        if not candidate.strip():
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed

    if last_error is not None:
        raise last_error
    raise json.JSONDecodeError("No JSON object found in reply", text, 0)


def _post(url: str, payload: bytes, api_key: str, timeout: int) -> str:
    """POST a JSON body and return the raw response text.

    Kept separate from :func:`chat_json` so the retry loop and the connection
    test share one request shape.
    """
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode()


def _completion_url(base_url: str) -> str:
    """Append the chat-completions path to an operator-supplied base URL.

    A base URL that already ends in ``/chat/completions`` is used verbatim, so
    an operator who pastes the full endpoint from a provider's docs is not
    silently given a doubled path.
    """
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    return f"{trimmed}/chat/completions"


def _extract_content(raw: str) -> str:
    """Pull the assistant message text out of an OpenAI-compatible envelope.

    Raises:
        LLMTruncatedError: when the reply stopped because it hit the token limit
            and therefore carries no answer. Reported separately from an empty
            reply so the caller can retry with a larger budget.
        LLMError: when the envelope carries no usable choice at all.
    """
    envelope = json.loads(raw)
    choices = envelope.get("choices") or []
    if not choices:
        raise LLMError(f"Gateway returned no choices: {raw[:200]}")

    content = (choices[0].get("message") or {}).get("content") or ""
    if content.strip():
        return content

    if llm_budget.is_truncated(envelope):
        reasoning = llm_budget.reasoning_tokens(envelope)
        raise LLMTruncatedError(
            "Model hit its token budget while still reasoning, so it produced no "
            f"answer (about {reasoning:,} reasoning tokens). Raising the budget "
            "and retrying."
        )
    raise LLMError("Gateway returned empty content")


def test_connection(
    overrides: dict | None = None, *, timeout_seconds: int = 60
) -> dict:
    """Probe an endpoint with a tiny request.

    The probe sends an **image** rather than plain text. Every AI feature in
    this app attaches one, so a text-only probe would report success for a model
    that then fails on every real call - the exact false confidence this check
    exists to prevent. The image is a 32x32 generated thumbnail, so it costs
    almost nothing.

    The token budget is deliberately generous. A reasoning model spends its
    allowance on a hidden chain of thought before answering, so a small cap
    (an earlier version used 16) makes a perfectly healthy endpoint report
    "returned empty content".

    Args:
        overrides: Unsaved candidate values to probe instead of the stored ones.
            Applying them to a copy of the configuration keeps "test" from
            pinning values the operator may still be experimenting with.
        timeout_seconds: Request timeout; a probe should fail fast, but reasoning
            models need longer than a text-only call would.

    Returns:
        ``{"ok": True, "model": ..., "reply": ...}`` on success, or
        ``{"ok": False, "error": "..."}``. Failures are returned rather than
        raised because every outcome here is a normal UI state.
    """
    cfg = app_settings.resolve_with(overrides)
    if not cfg.api_key:
        return {"ok": False, "error": "No API key configured."}

    try:
        probe_image = _probe_image_data_url()
    except Exception as exc:  # noqa: BLE001 - a probe must never raise
        return {"ok": False, "error": f"Could not build the probe image: {exc}"}

    budget = llm_budget.completion_token_budget(
        cfg.context_window, prompt=_PROBE_PROMPT, model=cfg.model
    )
    body = {
        "model": cfg.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROBE_PROMPT},
                    {"type": "image_url", "image_url": {"url": probe_image}},
                ],
            }
        ],
        "max_tokens": budget,
        "temperature": 0.0,
    }
    try:
        raw = _post(
            _completion_url(cfg.base_url),
            json.dumps(body).encode(),
            cfg.api_key,
            max(5, min(int(timeout_seconds), 180)),
        )
        reply = _extract_content(raw)
    except LLMTruncatedError as exc:
        # The endpoint and key are fine; only the budget was too small. Report
        # that distinctly so the operator does not go hunting for a bad key.
        return {
            "ok": False,
            "error": (
                "The endpoint replied but the model ran out of tokens while "
                f"reasoning ({exc}). This usually means the model needs a larger "
                "completion budget, not that the credentials are wrong."
            ),
        }
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()[:300]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001 - every failure is a UI message
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return {"ok": True, "model": cfg.model, "reply": reply.strip()[:80]}


def chat_json(
    image_path: str | Path,
    prompt: str,
    *,
    temperature: float = 0.1,
    max_attempts: int = 2,
) -> dict:
    """Send an image plus prompt to the gateway and parse a JSON object reply.

    Args:
        image_path: Path to the image to analyse.
        prompt: Instruction text; should ask for JSON only.
        temperature: Sampling temperature.
        max_attempts: Total attempts before giving up.

    Returns:
        The parsed JSON object.

    Raises:
        LLMError: if the key is missing, the file is unreadable, or every
            attempt fails or returns unparseable JSON.
    """
    cfg = app_settings.resolve()
    if not cfg.api_key:
        raise LLMError(
            "No LLM API key configured. Open Settings and enter one, or set "
            "LLM_API_KEY in the environment."
        )

    path = Path(image_path)
    if not path.exists():
        raise LLMError(f"File not found: {image_path}")

    try:
        data_url = _encode_image(path, cfg.image_max_dim)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Cannot read image: {exc}") from exc

    # Declaring a completion budget keeps a small window from being overrun by
    # an open-ended generation, which some gateways reject outright. The budget
    # grows on retry, because a reasoning model only reveals how much thinking
    # room it needs by exhausting the allowance once.
    max_tokens = llm_budget.completion_token_budget(
        cfg.context_window, prompt=prompt, model=cfg.model
    )

    url = _completion_url(cfg.base_url)
    last_error = "unknown error"
    # Tracked so that giving up preserves *why*: a caller (or an operator
    # reading the job report) needs to tell "the model ran out of room" apart
    # from "the endpoint is misconfigured".
    was_truncated = False

    for attempt in range(1, max_attempts + 1):
        body = {
            "model": cfg.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        payload = json.dumps(body).encode()

        try:
            content = _extract_content(_post(url, payload, cfg.api_key, cfg.timeout_seconds))
            return _extract_json(content)

        except LLMTruncatedError as exc:
            # The model thought itself out of budget. Ask for more room next
            # time rather than repeating the identical failing request.
            last_error = str(exc)
            was_truncated = True
            max_tokens = llm_budget.completion_token_budget(
                cfg.context_window,
                prompt=prompt,
                attempt=attempt + 1,
                model=cfg.model,
            )
            logger.warning(
                "LLM attempt %d truncated; retrying with max_tokens=%d (%s)",
                attempt,
                max_tokens,
                exc,
            )
        except LLMError as exc:
            last_error = str(exc)
            was_truncated = False
            logger.warning("LLM attempt %d: %s", attempt, last_error)
        except json.JSONDecodeError as exc:
            last_error = f"Response was not valid JSON: {exc}"
            was_truncated = False
            logger.warning("LLM attempt %d: %s", attempt, last_error)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            last_error = f"HTTP {exc.code}: {detail}"
            was_truncated = False
            logger.warning("LLM attempt %d: %s", attempt, last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            was_truncated = False
            logger.warning("LLM attempt %d: %s", attempt, last_error)

    # Preserve the distinction when giving up: a truncation is a budget problem
    # the operator can act on, not a bad endpoint or key.
    if was_truncated:
        raise LLMTruncatedError(last_error)
    raise LLMError(last_error)
