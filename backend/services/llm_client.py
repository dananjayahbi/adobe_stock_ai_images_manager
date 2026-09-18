"""OpenAI-compatible chat client for the local multi-provider LLM gateway.

The gateway (see Local-Multi-Provider-LLM-Router) exposes
``POST {base_url}/chat/completions`` and routes by the *virtual model name*
configured for a pool, e.g. ``OpenRouter-Free-Endpoint``.

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

from config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Raised when the gateway cannot be reached or returns an unusable reply."""


def _encode_image(path: Path, max_dim: int) -> str:
    """Read an image, downscale it, and return a base64 JPEG data URL.

    Downscaling keeps vision requests small; full-resolution AI images would
    otherwise push multi-megabyte payloads through the gateway.
    """
    with Image.open(path) as img:
        img = img.convert("RGB")
        if max(img.size) > max_dim:
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
    api_key = settings.effective_llm_api_key
    if not api_key:
        raise LLMError("No LLM API key configured (set LLM_API_KEY or GEMINI_API_KEY)")

    path = Path(image_path)
    if not path.exists():
        raise LLMError(f"File not found: {image_path}")

    try:
        data_url = _encode_image(path, settings.LLM_IMAGE_MAX_DIM)
    except Exception as exc:  # noqa: BLE001
        raise LLMError(f"Cannot read image: {exc}") from exc

    body = {
        "model": settings.LLM_MODEL,
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
        "response_format": {"type": "json_object"},
    }

    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = json.dumps(body).encode()
    last_error = "unknown error"

    for attempt in range(1, max_attempts + 1):
        request = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request, timeout=settings.LLM_TIMEOUT_SECONDS
            ) as response:
                raw = response.read().decode()

            envelope = json.loads(raw)
            choices = envelope.get("choices") or []
            if not choices:
                last_error = f"Gateway returned no choices: {raw[:200]}"
                logger.warning("LLM attempt %d: %s", attempt, last_error)
                continue

            content = (choices[0].get("message") or {}).get("content") or ""
            if not content.strip():
                last_error = "Gateway returned empty content"
                logger.warning("LLM attempt %d: %s", attempt, last_error)
                continue

            return _extract_json(content)

        except json.JSONDecodeError as exc:
            last_error = f"Response was not valid JSON: {exc}"
            logger.warning("LLM attempt %d: %s", attempt, last_error)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            last_error = f"HTTP {exc.code}: {detail}"
            logger.warning("LLM attempt %d: %s", attempt, last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LLM attempt %d: %s", attempt, last_error)

    raise LLMError(last_error)
