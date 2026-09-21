"""Runtime application settings that the operator can change without a restart.

Why this exists
---------------
The LLM endpoint used to be fixed at startup by ``.env``. Switching to another
OpenAI-compatible provider (or pointing at a different local gateway) meant
editing a file and restarting uvicorn. This module lets the Settings modal read
and write that configuration while the server keeps running.

Layering (later wins)
---------------------
1. Built-in defaults declared here.
2. Environment / ``.env``, exposed as fields on :class:`config.Settings`.
3. This store - what the operator saved in the Settings modal.

The store is a small JSON document rather than a SQLite table because these are
a handful of operator preferences, not relational data. Keeping the API key in a
separate file also keeps it out of the database, so exporting or sharing
``adobe_stock.db`` never leaks credentials.

Secrets
-------
:func:`read_public` never returns a usable key. It returns a masked form
(``••••••••abcd``) plus an ``api_key_set`` flag, and :func:`update` treats an
empty value *or* the mask itself as "leave the stored key alone". That is the
same contract GitHub uses for personal access tokens, and it means a UI that
round-trips the masked value cannot accidentally blank a working key.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from config import settings
from services import llm_budget

logger = logging.getLogger(__name__)

#: Bumped when the on-disk shape changes in a way that needs migration.
SETTINGS_VERSION = 1

#: Used when neither the store nor the environment states a context window.
#: The environment layer is ``config.Settings.LLM_CONTEXT_WINDOW``; this is the
#: final fallback, applied through :func:`_env_context_window` so the two are
#: read in one place and cannot silently disagree.
DEFAULT_CONTEXT_WINDOW = 32_768
MIN_CONTEXT_WINDOW = 4_096
MAX_CONTEXT_WINDOW = 2_000_000

#: Characters shown in place of the stored API key. Deliberately ASCII: the
#: masked value is echoed back by the client and compared against a freshly
#: generated mask, so a multi-byte character could mismatch if any hop in the
#: chain disagrees about encoding - which would store the mask *as* the key.
_MASK_FILL = "********"
_MASK_TAIL = 4

#: Only http(s) endpoints are accepted; a stray scheme would be a silent no-op.
_ALLOWED_SCHEMES = ("http://", "https://")


@dataclass(frozen=True)
class LlmConfig:
    """The effective LLM endpoint configuration, after all layers are applied."""

    base_url: str
    model: str
    api_key: str
    context_window: int
    timeout_seconds: int
    #: Ceiling on the long edge of an image sent to a vision model.
    image_max_dim: int
    #: True when a key is available at all (a request would be attempted).
    has_api_key: bool


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #

def _path() -> Path:
    """Resolve the store path from settings on every call.

    Reading the attribute each time (rather than caching a module constant) is
    what lets the test suite redirect the store into a tmp directory.
    """
    return Path(getattr(settings, "APP_SETTINGS_PATH", Path("app_settings.json")))


def load_raw() -> dict[str, Any]:
    """Read the stored document, returning ``{}`` when there is nothing usable.

    A missing, empty, or corrupt file is not an error: the operator simply gets
    the environment defaults, which is exactly the state before the modal has
    ever been used. The corrupt case is logged because it means a save was
    interrupted.
    """
    path = _path()
    try:
        if not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read %s; falling back to environment defaults", path)
        return {}

    if not isinstance(data, dict):
        logger.warning("%s did not contain a JSON object; ignoring it", path)
        return {}
    return data


def save_raw(data: dict[str, Any]) -> None:
    """Write the document atomically so an interrupted save cannot corrupt it."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": SETTINGS_VERSION, **data}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Masking
# --------------------------------------------------------------------------- #

def mask_key(key: str) -> str:
    """Return a display-only form of an API key.

    Short keys are masked entirely rather than partially revealed, because
    showing the tail of an 8-character key would disclose half of it.
    """
    if not key:
        return ""
    if len(key) <= _MASK_TAIL + 2:
        return _MASK_FILL
    return f"{_MASK_FILL}{key[-_MASK_TAIL:]}"


def _is_mask(value: str, stored: str) -> bool:
    """True when ``value`` is the masked placeholder for ``stored``.

    The mask is regenerated from the stored key rather than compared against a
    fixed string, so a client echoing back exactly what :func:`read_public`
    returned is always recognised as "unchanged".
    """
    if not value:
        return True
    return bool(stored) and value == mask_key(stored)


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #

def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _stored_int(raw: dict[str, Any], key: str, fallback: int) -> int:
    """Read a stored integer, clamped into its valid range.

    Clamping rather than rejecting means a hand-edited file with an absurd value
    degrades to something usable instead of breaking every LLM call.
    """
    if raw.get(key) is None:
        return fallback
    parsed = _int_or(raw.get(key), fallback)
    return max(MIN_CONTEXT_WINDOW, min(MAX_CONTEXT_WINDOW, parsed))


def _env_context_window() -> int:
    """The environment-level context window, clamped into the supported range.

    ``LLM_CONTEXT_WINDOW`` is the operator's way to state the window in ``.env``
    for a model whose size we cannot guess; a value saved in the store overrides
    it. Clamping keeps a typo from producing an unusable configuration.
    """
    configured = _int_or(
        getattr(settings, "LLM_CONTEXT_WINDOW", DEFAULT_CONTEXT_WINDOW),
        DEFAULT_CONTEXT_WINDOW,
    )
    return max(MIN_CONTEXT_WINDOW, min(MAX_CONTEXT_WINDOW, configured))


def resolve() -> LlmConfig:
    """Merge the three layers into the configuration a request should use."""
    raw = load_raw()

    base_url = str(raw.get("llm_base_url") or "").strip() or settings.LLM_BASE_URL
    model = str(raw.get("llm_model") or "").strip() or settings.LLM_MODEL
    api_key = str(raw.get("llm_api_key") or "").strip() or settings.effective_llm_api_key
    context_window = _stored_int(raw, "llm_context_window", _env_context_window())

    env_dim = _int_or(getattr(settings, "LLM_IMAGE_MAX_DIM", 1024), 1024)
    return LlmConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,
        context_window=context_window,
        timeout_seconds=_int_or(getattr(settings, "LLM_TIMEOUT_SECONDS", 240), 240),
        image_max_dim=llm_budget.resolve_image_max_dim(context_window, env_dim),
        has_api_key=bool(api_key),
    )


def read_public() -> dict[str, Any]:
    """The payload the Settings modal renders.

    ``effective_*`` fields are what a request would actually use right now,
    which is what the operator needs to see when the store is empty and the
    values come from ``.env``.
    """
    raw = load_raw()
    effective = resolve()
    return {
        "llm_base_url": str(raw.get("llm_base_url") or "").strip(),
        "llm_model": str(raw.get("llm_model") or "").strip(),
        "llm_api_key_masked": mask_key(effective.api_key),
        "llm_api_key_set": effective.has_api_key,
        "llm_context_window": _stored_int(raw, "llm_context_window", _env_context_window()),
        "effective_base_url": effective.base_url,
        "effective_model": effective.model,
        "effective_context_window": effective.context_window,
        "effective_image_max_dim": effective.image_max_dim,
        "defaults": {
            "llm_base_url": settings.LLM_BASE_URL,
            "llm_model": settings.LLM_MODEL,
            "llm_context_window": _env_context_window(),
        },
        "bounds": {
            "min_context_window": MIN_CONTEXT_WINDOW,
            "max_context_window": MAX_CONTEXT_WINDOW,
        },
    }


# --------------------------------------------------------------------------- #
# Update
# --------------------------------------------------------------------------- #

class SettingsValidationError(ValueError):
    """Raised when a submitted value cannot be stored."""


def _clean_url(value: str) -> str:
    """Validate and normalise an OpenAI-compatible base URL.

    A trailing ``/v1``-style path is preserved; only a trailing slash is
    removed, because ``chat_json`` appends ``/chat/completions`` itself and a
    doubled slash confuses some gateways.
    """
    url = (value or "").strip().rstrip("/")
    if not url:
        raise SettingsValidationError("Base URL is required.")
    if not url.lower().startswith(_ALLOWED_SCHEMES):
        raise SettingsValidationError(
            "Base URL must start with http:// or https:// (include the /v1 path when the "
            "provider needs one)."
        )
    return url


def _clean_window(value: Any) -> int:
    """Validate a context window, rejecting anything outside the supported range."""
    window = _int_or(value, -1)
    if window < MIN_CONTEXT_WINDOW or window > MAX_CONTEXT_WINDOW:
        raise SettingsValidationError(
            f"Context window must be between {MIN_CONTEXT_WINDOW:,} and "
            f"{MAX_CONTEXT_WINDOW:,} tokens."
        )
    return window


def validate(payload: dict[str, Any]) -> None:
    """Check a payload without storing it.

    Used by the connection probe, which must reject an unusable candidate with
    the same message a save would give, but must not write anything.
    """
    if payload.get("llm_base_url") is not None:
        _clean_url(str(payload["llm_base_url"]))
    if payload.get("llm_model") is not None and not str(payload["llm_model"]).strip():
        raise SettingsValidationError("Model ID is required.")
    if payload.get("llm_context_window") is not None:
        _clean_window(payload["llm_context_window"])


def resolve_with(overrides: dict[str, Any] | None = None) -> LlmConfig:
    """The configuration a request would use, with unsaved candidates applied.

    This is what makes the connection probe non-destructive: the operator can
    verify a candidate endpoint without the act of testing it pinning the
    values into the store. An empty or masked API key override means "keep the
    effective key", matching the save contract.
    """
    base = resolve()
    if not overrides:
        return base

    base_url = str(overrides.get("llm_base_url") or "").strip()
    model = str(overrides.get("llm_model") or "").strip()
    submitted_key = str(overrides.get("llm_api_key") or "").strip()
    window = overrides.get("llm_context_window")

    resolved_key = base.api_key
    if submitted_key and not _is_mask(submitted_key, base.api_key):
        resolved_key = submitted_key

    context_window = (
        _clean_window(window) if window is not None else base.context_window
    )

    return replace(
        base,
        base_url=_clean_url(base_url) if base_url else base.base_url,
        model=model or base.model,
        api_key=resolved_key,
        has_api_key=bool(resolved_key),
        context_window=context_window,
        image_max_dim=llm_budget.resolve_image_max_dim(
            context_window, base.image_max_dim
        ),
    )


def update(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a partial update and return the new public view.

    Only keys present in ``payload`` are touched, so the modal can submit a
    single field without clearing the rest. An ``llm_api_key`` that is empty or
    equal to the current mask keeps the stored key; pass
    ``clear_api_key: true`` to remove it deliberately.
    """
    stored = load_raw()
    effective = resolve()

    if "llm_base_url" in payload and payload["llm_base_url"] is not None:
        stored["llm_base_url"] = _clean_url(str(payload["llm_base_url"]))

    if "llm_model" in payload and payload["llm_model"] is not None:
        model = str(payload["llm_model"]).strip()
        if not model:
            raise SettingsValidationError("Model ID is required.")
        stored["llm_model"] = model

    if "llm_context_window" in payload and payload["llm_context_window"] is not None:
        stored["llm_context_window"] = _clean_window(payload["llm_context_window"])

    if payload.get("clear_api_key"):
        # Remove the key rather than storing an empty string, so resolution
        # falls through to the environment exactly as it would if the operator
        # had never saved anything. Storing "" would *shadow* an .env key and
        # make "clear" behave differently from "never set".
        stored.pop("llm_api_key", None)
    elif "llm_api_key" in payload and payload["llm_api_key"] is not None:
        submitted = str(payload["llm_api_key"])
        # A value that is blank, whitespace, or the mask we handed out means the
        # operator did not change the key - never blank a working credential.
        if not _is_mask(submitted.strip(), effective.api_key):
            stored["llm_api_key"] = submitted.strip()

    save_raw(stored)
    logger.info("Application settings updated")
    return read_public()
