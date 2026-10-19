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

#: The mask used for the Brave search key. A distinct prefix so a key echoed back
#: from the wrong field is still recognised as "unchanged" rather than stored.
BRAVE_MASK_PREFIX = "brave"

#: Bounds on the stored rate limit. Below 0.1 req/s a single ``market_overview``
#: call would take a minute; above 10 the pacing stops having any effect.
MIN_BRAVE_RATE = 0.1
MAX_BRAVE_RATE = 10.0

#: Bounds on the research agent's tool budget. Mirrors
#: ``services.research.agent.MIN_TOOL_CALLS``/``MAX_TOOL_CALLS``; duplicated as
#: numbers rather than imported because ``app_settings`` is application-level and
#: must not depend on a feature package.
MIN_TOOL_CALLS = 4
MAX_TOOL_CALLS = 80

#: Bounds on the metadata generator. Adobe's CSV ceiling is 49 keywords; asking
#: for fewer is an economy choice, never more than the portal accepts.
MIN_KEYWORD_TARGET = 5
MAX_KEYWORD_TARGET = 49
#: Seconds between metadata calls (the gateway routes to free, rate-limited models).
MIN_METADATA_DELAY = 0.0
MAX_METADATA_DELAY = 30.0
#: Operator notes appended verbatim to the metadata prompt. Bounded so a paste
#: cannot blow past the model's context window.
MAX_EXTRA_INSTRUCTIONS = 2_000
#: Upper bound on the operator's priority keyword list - the formatter moves
#: these to the front, and past ~40 terms the "priority" ordering is noise.
MAX_PRIORITY_TERMS_CHARS = 2_000

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


@dataclass(frozen=True)
class SearchConfig:
    """The effective web-search configuration for the research agent.

    Separate from :class:`LlmConfig` because the two have nothing to do with each
    other — a search provider is not an LLM endpoint — and folding the key into the
    LLM config would make "which credential is this?" ambiguous at every call site.

    ``enabled`` and ``has_api_key`` are both needed: "the operator turned it on"
    and "it can actually be used" are different states, and the second is what
    decides the provider order.
    """

    enabled: bool
    api_key: str
    has_api_key: bool
    rate_limit_per_second: float
    #: True when Brave will actually be tried first. Derived rather than stored,
    #: so the UI cannot show "active" for a provider with no key.
    uses_brave: bool


@dataclass(frozen=True)
class MetadataConfig:
    """Effective metadata-generation options (title/keywords/category).

    Kept apart from :class:`LlmConfig` because these are *content* choices -
    how many keywords to ask for, how hard to pace the calls, what extra
    instruction to append - not endpoint choices.
    """

    keyword_target: int
    delay_seconds: float
    extra_instructions: str
    #: High-intent commercial terms moved to the first keyword positions.
    priority_terms: tuple[str, ...] = ()


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


def mask_brave_key(key: str) -> str:
    """Display-only form of the Brave search key.

    Prefixed so the two credentials in the settings payload are never mistaken
    for one another by the UI or by a client that echoes a mask back.
    """
    masked = mask_key(key)
    return f"{BRAVE_MASK_PREFIX}:{masked}" if masked else ""


def _is_mask(value: str, stored: str) -> bool:
    """True when ``value`` is the masked placeholder for ``stored``.

    The mask is regenerated from the stored key rather than compared against a
    fixed string, so a client echoing back exactly what :func:`read_public`
    returned is always recognised as "unchanged".
    """
    if not value:
        return True
    return bool(stored) and value == mask_key(stored)


def _is_brave_mask(value: str, stored: str) -> bool:
    """The Brave equivalent of :func:`_is_mask`.

    Accepts both the prefixed mask this module hands out and a bare one, so a
    client that strips the prefix cannot blank a working key.
    """
    if not value:
        return True
    return bool(stored) and value in (mask_brave_key(stored), mask_key(stored))


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


def _env_brave_enabled() -> bool:
    """Whether ``.env`` turns Brave on, so a deployment can set it once."""
    return bool(getattr(settings, "BRAVE_SEARCH_ENABLED", False))


def _env_brave_key() -> str:
    """The Brave key from ``.env``, the fallback when none is stored."""
    return str(getattr(settings, "BRAVE_SEARCH_API_KEY", "") or "").strip()


def _env_brave_rate() -> float:
    """The plan's allowed requests per second, clamped to the supported range."""
    raw = getattr(settings, "BRAVE_SEARCH_RATE_LIMIT_PER_SECOND", 1.0)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = 1.0
    return max(MIN_BRAVE_RATE, min(MAX_BRAVE_RATE, value))


def resolve_search() -> SearchConfig:
    """The effective web-search configuration, after all layers are applied.

    Mirrors :func:`resolve` for the LLM endpoint: stored value first, then
    ``.env``, then the built-in default. ``uses_brave`` is the single decision the
    provider chain consults, so "enabled but no key" cannot half-enable the
    feature and leave the agent on a provider it cannot authenticate to.
    """
    raw = load_raw()

    stored_enabled = raw.get("brave_search_enabled")
    enabled = (
        bool(stored_enabled) if isinstance(stored_enabled, bool) else _env_brave_enabled()
    )
    api_key = str(raw.get("brave_search_api_key") or "").strip() or _env_brave_key()
    rate = raw.get("brave_search_rate_limit")
    rate_limit = (
        _clean_brave_rate(rate) if rate is not None else _env_brave_rate()
    )

    return SearchConfig(
        enabled=enabled,
        api_key=api_key,
        has_api_key=bool(api_key),
        rate_limit_per_second=rate_limit,
        uses_brave=enabled and bool(api_key),
    )


def _env_keyword_target() -> int:
    value = _int_or(getattr(settings, "METADATA_KEYWORD_TARGET", 49), 49)
    return max(MIN_KEYWORD_TARGET, min(MAX_KEYWORD_TARGET, value))


def _env_metadata_delay() -> float:
    try:
        value = float(getattr(settings, "METADATA_CALL_DELAY_SECONDS", 2.0))
    except (TypeError, ValueError):
        value = 2.0
    return max(MIN_METADATA_DELAY, min(MAX_METADATA_DELAY, value))


def resolve_metadata() -> MetadataConfig:
    """The effective metadata-generation options.

    Resolved per call (not at import) so a Settings change reaches the very next
    metadata generation with no restart - the same contract as the LLM endpoint.
    """
    raw = load_raw()

    target = raw.get("metadata_keyword_target")
    keyword_target = (
        max(MIN_KEYWORD_TARGET, min(MAX_KEYWORD_TARGET, _int_or(target, 49)))
        if target is not None
        else _env_keyword_target()
    )
    delay = raw.get("metadata_delay_seconds")
    delay_seconds = (
        max(MIN_METADATA_DELAY, min(MAX_METADATA_DELAY, _clean_delay(delay)))
        if delay is not None
        else _env_metadata_delay()
    )
    extra = str(raw.get("metadata_extra_instructions") or "").strip()
    from services.metadata_formatter import parse_priority_terms

    priority = parse_priority_terms(raw.get("metadata_priority_terms"))
    return MetadataConfig(
        keyword_target=keyword_target,
        delay_seconds=delay_seconds,
        extra_instructions=extra[:MAX_EXTRA_INSTRUCTIONS],
        priority_terms=priority,
    )


def resolve_tool_budget() -> int:
    """The research agent's tool budget, from the store or the built-in default.

    Resolved per run rather than captured at import, so raising it in Settings
    takes effect on the next turn with no restart — the same contract the context
    window and the LLM endpoint already have.
    """
    raw = load_raw()
    stored = raw.get("research_max_tool_calls")
    if stored is None:
        from services.research import agent as agent_module

        return agent_module.DEFAULT_MAX_TOOL_CALLS
    try:
        return _clean_tool_calls(stored)
    except SettingsValidationError:
        # A hand-edited store must not break every research run; fall back and say
        # so, rather than raising on a read path.
        from services.research import agent as agent_module

        logger.warning(
            "Stored research_max_tool_calls=%r is out of range; using the default",
            stored,
        )
        return agent_module.DEFAULT_MAX_TOOL_CALLS


def read_public() -> dict[str, Any]:
    """The payload the Settings modal renders.

    ``effective_*`` fields are what a request would actually use right now,
    which is what the operator needs to see when the store is empty and the
    values come from ``.env``.
    """
    raw = load_raw()
    effective = resolve()
    search = resolve_search()
    meta = resolve_metadata()
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
        "brave_search_enabled": search.enabled,
        "brave_search_api_key_masked": mask_brave_key(search.api_key),
        "brave_search_api_key_set": search.has_api_key,
        "brave_search_rate_limit": search.rate_limit_per_second,
        # The resolved answer to "which provider will actually run first".
        # Derived so the UI cannot claim Brave is active for an enabled-but-
        # keyless configuration.
        "effective_uses_brave": search.uses_brave,
        "effective_search_provider": (
            "brave" if search.uses_brave else "duckduckgo"
        ),
        "research_max_tool_calls": resolve_tool_budget(),
        # Metadata generation - content choices, resolved so the UI shows what
        # the next generation will actually use.
        "metadata_keyword_target": meta.keyword_target,
        "metadata_delay_seconds": meta.delay_seconds,
        "metadata_extra_instructions": meta.extra_instructions,
        "metadata_priority_terms": ", ".join(meta.priority_terms),
        # Source folder for the browse/import APIs. Not a secret - it is shown
        # (and edited) as-is so the operator can verify the exact path.
        "source_folder": str(raw.get("source_folder") or "").strip(),
        "defaults": {
            "llm_base_url": settings.LLM_BASE_URL,
            "llm_model": settings.LLM_MODEL,
            "llm_context_window": _env_context_window(),
        },
        "bounds": {
            "min_context_window": MIN_CONTEXT_WINDOW,
            "max_context_window": MAX_CONTEXT_WINDOW,
            "min_brave_rate": MIN_BRAVE_RATE,
            "max_brave_rate": MAX_BRAVE_RATE,
            "min_tool_calls": MIN_TOOL_CALLS,
            "max_tool_calls": MAX_TOOL_CALLS,
            "min_keyword_target": MIN_KEYWORD_TARGET,
            "max_keyword_target": MAX_KEYWORD_TARGET,
            "min_metadata_delay": MIN_METADATA_DELAY,
            "max_metadata_delay": MAX_METADATA_DELAY,
            "max_extra_instructions": MAX_EXTRA_INSTRUCTIONS,
            "max_priority_terms_chars": MAX_PRIORITY_TERMS_CHARS,
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


def _clean_brave_rate(value: Any) -> float:
    """Validate the Brave rate limit.

    Rejected outside the range rather than clamped: a rate the operator did not
    intend is a silent behaviour change to how long every research run takes.
    """
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise SettingsValidationError(
            "Brave rate limit must be a number of requests per second."
        ) from None
    if rate < MIN_BRAVE_RATE or rate > MAX_BRAVE_RATE:
        raise SettingsValidationError(
            f"Brave rate limit must be between {MIN_BRAVE_RATE:g} and "
            f"{MAX_BRAVE_RATE:g} requests per second."
        )
    return rate


def _clean_tool_calls(value: Any) -> int:
    """Validate the research tool budget."""
    calls = _int_or(value, -1)
    if calls < MIN_TOOL_CALLS or calls > MAX_TOOL_CALLS:
        raise SettingsValidationError(
            f"Research tool limit must be between {MIN_TOOL_CALLS} and "
            f"{MAX_TOOL_CALLS} calls."
        )
    return calls


def _clean_keyword_target(value: Any) -> int:
    """Validate the number of keywords the metadata model is asked for."""
    target = _int_or(value, -1)
    if target < MIN_KEYWORD_TARGET or target > MAX_KEYWORD_TARGET:
        raise SettingsValidationError(
            f"Keyword target must be between {MIN_KEYWORD_TARGET} and "
            f"{MAX_KEYWORD_TARGET}."
        )
    return target


def _clean_delay(value: Any) -> float:
    """Validate the pause between metadata calls."""
    try:
        delay = float(value)
    except (TypeError, ValueError):
        raise SettingsValidationError(
            "Metadata delay must be a number of seconds."
        ) from None
    if delay < MIN_METADATA_DELAY or delay > MAX_METADATA_DELAY:
        raise SettingsValidationError(
            f"Metadata delay must be between {MIN_METADATA_DELAY:g} and "
            f"{MAX_METADATA_DELAY:g} seconds."
        )
    return delay


def _clean_extra_instructions(value: Any) -> str:
    """Validate the operator's appended metadata instructions."""
    text = str(value or "").strip()
    if len(text) > MAX_EXTRA_INSTRUCTIONS:
        raise SettingsValidationError(
            f"Extra instructions must be {MAX_EXTRA_INSTRUCTIONS} characters or fewer."
        )
    return text


def _clean_priority_terms(value: Any) -> str:
    """Validate the operator's comma-separated priority keyword list."""
    text = str(value or "").strip()
    if len(text) > MAX_PRIORITY_TERMS_CHARS:
        raise SettingsValidationError(
            f"Priority terms must be {MAX_PRIORITY_TERMS_CHARS} characters or fewer."
        )
    return text


def _clean_source_folder(value: Any) -> str:
    """Normalise the source folder: a plain trimmed path, no secrecy.

    ``""`` is a legal value and clears the setting — the browse/import APIs
    treat an empty string as "not configured" rather than as a path.
    """
    return str(value or "").strip()


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
    if payload.get("brave_search_rate_limit") is not None:
        _clean_brave_rate(payload["brave_search_rate_limit"])
    if payload.get("research_max_tool_calls") is not None:
        _clean_tool_calls(payload["research_max_tool_calls"])
    if payload.get("metadata_keyword_target") is not None:
        _clean_keyword_target(payload["metadata_keyword_target"])
    if payload.get("metadata_delay_seconds") is not None:
        _clean_delay(payload["metadata_delay_seconds"])
    if payload.get("metadata_extra_instructions") is not None:
        _clean_extra_instructions(payload["metadata_extra_instructions"])
    if payload.get("metadata_priority_terms") is not None:
        _clean_priority_terms(payload["metadata_priority_terms"])
    if payload.get("source_folder") is not None:
        _clean_source_folder(payload["source_folder"])
    # Enabling Brave without a usable key is refused *here* rather than at search
    # time. A configuration that looks enabled and silently is not is worse than a
    # rejected save: the operator would believe their searches were going through
    # Brave and never learn otherwise.
    if payload.get("brave_search_enabled") and not payload.get("clear_brave_search_key"):
        candidate = str(payload.get("brave_search_api_key") or "").strip()
        effective = resolve_search()
        if not candidate or _is_brave_mask(candidate, effective.api_key):
            if not effective.has_api_key:
                raise SettingsValidationError(
                    "Brave Search needs an API key before it can be enabled."
                )


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

    Validated with the same :func:`validate` the connection probe uses, so a save
    cannot accept a payload the probe would have rejected — the two paths giving
    different answers about the same values is how a UI ends up offering a
    configuration the backend then refuses.
    """
    validate(payload)
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

    # --- web search ----------------------------------------------------- #
    # Same key contract as the LLM credential: a blank or masked value means
    # "unchanged", and clearing removes the key rather than storing "" so the
    # ``.env`` value is reachable again.
    if "brave_search_rate_limit" in payload and payload["brave_search_rate_limit"] is not None:
        stored["brave_search_rate_limit"] = _clean_brave_rate(
            payload["brave_search_rate_limit"]
        )

    search = resolve_search()
    if payload.get("clear_brave_search_key"):
        stored.pop("brave_search_api_key", None)
    elif "brave_search_api_key" in payload and payload["brave_search_api_key"] is not None:
        submitted = str(payload["brave_search_api_key"]).strip()
        if not _is_brave_mask(submitted, search.api_key):
            stored["brave_search_api_key"] = submitted

    if "brave_search_enabled" in payload and payload["brave_search_enabled"] is not None:
        stored["brave_search_enabled"] = bool(payload["brave_search_enabled"])

    if "research_max_tool_calls" in payload and payload["research_max_tool_calls"] is not None:
        stored["research_max_tool_calls"] = _clean_tool_calls(
            payload["research_max_tool_calls"]
        )

    # --- metadata generation ------------------------------------------- #
    if "metadata_keyword_target" in payload and payload["metadata_keyword_target"] is not None:
        stored["metadata_keyword_target"] = _clean_keyword_target(
            payload["metadata_keyword_target"]
        )
    if "metadata_delay_seconds" in payload and payload["metadata_delay_seconds"] is not None:
        stored["metadata_delay_seconds"] = _clean_delay(
            payload["metadata_delay_seconds"]
        )
    if "metadata_extra_instructions" in payload and payload["metadata_extra_instructions"] is not None:
        stored["metadata_extra_instructions"] = _clean_extra_instructions(
            payload["metadata_extra_instructions"]
        )
    if "metadata_priority_terms" in payload and payload["metadata_priority_terms"] is not None:
        stored["metadata_priority_terms"] = _clean_priority_terms(
            payload["metadata_priority_terms"]
        )

    # --- source folder (browse/import APIs) ------------------------------ #
    # Plain string: trimmed, stored verbatim; "" clears the setting.
    if payload.get("source_folder") is not None:
        stored["source_folder"] = _clean_source_folder(payload["source_folder"])

    save_raw(stored)
    logger.info("Application settings updated")
    return read_public()
