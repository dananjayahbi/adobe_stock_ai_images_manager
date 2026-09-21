"""Tests for the OpenAI-compatible LLM gateway client and its consumers.

Network calls are stubbed so these run offline; the goal is to pin the
request shape and the error/parse handling, not the provider behaviour.
"""

import io
import json

import pytest

from services import gemini_auditor, gemini_metadata, llm_budget, llm_client
from services.llm_client import LLMError, LLMTruncatedError


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _truncated_envelope(reasoning_chars: int = 4000) -> dict:
    """A reasoning model that spent its whole budget thinking and never answered.

    This is the exact shape measured from ``deepseek-v4.1-flash``: the chain of
    thought lands in ``reasoning_content``, ``content`` is empty, and
    ``finish_reason`` is ``"length"``.
    """
    return {
        "id": "gen-truncated",
        "object": "chat.completion",
        "model": "reasoning-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": "length",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "x" * reasoning_chars,
                },
            }
        ],
        "usage": {"completion_tokens_details": {"reasoning_tokens": 2503}},
    }


def _envelope(content: str) -> dict:
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "model": "some/pool-member:free",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


@pytest.fixture()
def capture_request(monkeypatch):
    """Capture the outgoing request and return a canned reply."""
    captured: dict = {}
    reply: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return _FakeResponse(reply["payload"])

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)
    return captured, reply


@pytest.fixture()
def sample_image(tmp_path):
    from PIL import Image

    path = tmp_path / "img.jpg"
    Image.new("RGB", (64, 64), (200, 100, 50)).save(path, "JPEG")
    return path


def test_chat_json_builds_openai_compatible_request(
    capture_request, sample_image, monkeypatch
):
    from config import settings

    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://localhost:4006/api/gateway/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "OpenRouter-Free-Endpoint")
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    result = llm_client.chat_json(sample_image, "analyse this")

    assert result == {"ok": True}
    assert captured["url"] == "http://localhost:4006/api/gateway/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"

    body = captured["body"]
    assert body["model"] == "OpenRouter-Free-Endpoint"
    assert body["response_format"] == {"type": "json_object"}

    content = body["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "analyse this"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_chat_json_strips_markdown_fences(capture_request, sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope('```json\n{"a": 1}\n```')

    assert llm_client.chat_json(sample_image, "p") == {"a": 1}


def test_chat_json_extracts_json_from_surrounding_prose(
    capture_request, sample_image, monkeypatch
):
    """Free models often wrap JSON in explanation text."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope(
        'Sure! Here is the analysis:\n{"confidence_score": 0.8, "flags": []}\nHope that helps.'
    )

    assert llm_client.chat_json(sample_image, "p") == {
        "confidence_score": 0.8,
        "flags": [],
    }


def test_chat_json_retries_then_succeeds(capture_request, sample_image, monkeypatch):
    """A malformed first reply should not fail the call if a retry parses."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    payloads = [_envelope("no json here at all"), _envelope('{"ok": 1}')]
    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode())
        payload = payloads[min(calls["n"], len(payloads) - 1)]
        calls["n"] += 1
        return _FakeResponse(payload)

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    assert llm_client.chat_json(sample_image, "p") == {"ok": 1}
    assert calls["n"] == 2


def test_chat_json_gives_up_after_max_attempts(sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        return _FakeResponse(_envelope("definitely not json"))

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LLMError):
        llm_client.chat_json(sample_image, "p", max_attempts=3)

    assert calls["n"] == 3


def test_chat_json_raises_without_api_key(sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    with pytest.raises(LLMError, match="No LLM API key"):
        llm_client.chat_json(sample_image, "p")


def test_chat_json_raises_on_missing_file(tmp_path, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    with pytest.raises(LLMError, match="File not found"):
        llm_client.chat_json(tmp_path / "nope.jpg", "p")


# --------------------------------------------------------------------------- #
# Reasoning models
# --------------------------------------------------------------------------- #

def test_truncated_reply_is_reported_as_truncation_not_emptiness(
    sample_image, monkeypatch
):
    """The bug: an empty ``content`` from a reasoning model looked like no reply.

    The endpoint is healthy and the credentials are correct; the model simply
    spent its whole allowance on a hidden chain of thought.
    """
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        return _FakeResponse(_truncated_envelope())

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LLMTruncatedError, match="reasoning"):
        llm_client.chat_json(sample_image, "p", max_attempts=1)


def test_chat_json_retries_with_a_bigger_budget_after_truncation(
    sample_image, monkeypatch
):
    """Truncation must escalate the budget, not repeat the failing request."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 200_000)

    budgets: list[int] = []

    def fake_urlopen(request, timeout=None):
        budgets.append(json.loads(request.data.decode())["max_tokens"])
        if len(budgets) == 1:
            return _FakeResponse(_truncated_envelope())
        return _FakeResponse(_envelope('{"ok": true}'))

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    assert llm_client.chat_json(sample_image, "p", max_attempts=2) == {"ok": True}
    assert len(budgets) == 2
    assert budgets[1] > budgets[0], f"budget did not grow: {budgets}"


def test_truncation_is_survivable_when_the_retry_also_truncates(
    sample_image, monkeypatch
):
    """Exhausting the retries yields a normal LLMError, not a crash."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    calls = {"n": 0}

    def fake_urlopen(request, timeout=None):
        calls["n"] += 1
        return _FakeResponse(_truncated_envelope())

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LLMError):
        llm_client.chat_json(sample_image, "p", max_attempts=3)

    assert calls["n"] == 3


def test_a_large_context_window_gets_a_budget_a_reasoning_model_can_use(
    capture_request, sample_image, monkeypatch
):
    """The old hard 4096 cap is what broke the reasoning model.

    Measured on this repo's metadata prompt, a single pass spent 2,503 reasoning
    tokens for an 867-character answer, and another spent 8,054 - so a 4096 cap
    truncates before the model has even started writing.
    """
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 200_000)

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.chat_json(sample_image, "p")

    assert captured["body"]["max_tokens"] > 4096


def test_budget_never_exceeds_the_context_window(
    capture_request, sample_image, monkeypatch
):
    """A budget larger than the window would be rejected outright."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 8192)

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.chat_json(sample_image, "p")

    assert captured["body"]["max_tokens"] <= 8192


# --------------------------------------------------------------------------- #
# Settings-driven resolution
# --------------------------------------------------------------------------- #

def test_chat_json_uses_the_endpoint_saved_in_settings(
    capture_request, sample_image, monkeypatch
):
    """The Settings modal must change where requests go, without a restart."""
    from config import settings
    from services import app_settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-env")
    app_settings.update(
        {
            "llm_base_url": "https://api.example.com/v1",
            "llm_model": "vision-model-1",
            "llm_api_key": "sk-from-settings",
            "llm_context_window": 131072,
        }
    )

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.chat_json(sample_image, "p")

    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-from-settings"
    assert captured["body"]["model"] == "vision-model-1"


def test_chat_json_accepts_a_base_url_that_already_has_the_path(
    capture_request, sample_image, monkeypatch
):
    """Pasting the full endpoint from a provider's docs must not double the path."""
    from config import settings
    from services import app_settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    app_settings.update({"llm_base_url": "https://api.example.com/v1/chat/completions"})

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.chat_json(sample_image, "p")

    assert captured["url"] == "https://api.example.com/v1/chat/completions"


def test_chat_json_declares_a_completion_budget(capture_request, sample_image, monkeypatch):
    """A declared budget stops an open-ended generation overrunning the window."""
    from config import settings
    from services import app_settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    app_settings.update({"llm_context_window": 8192})

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.chat_json(sample_image, "p")

    max_tokens = captured["body"]["max_tokens"]
    # A 8k window cannot afford much of a reply, so the budget is clamped to
    # what is actually available rather than the model's full ceiling.
    assert 256 <= max_tokens <= 8192


def test_a_smaller_context_window_lowers_the_completion_budget(
    capture_request, sample_image, monkeypatch
):
    """The declared window must actually constrain what we ask for."""
    from config import settings
    from services import app_settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    # A prompt large enough to consume most of a small window.
    long_prompt = "x" * 20_000

    app_settings.update({"llm_context_window": 8192})
    llm_client.chat_json(sample_image, long_prompt)
    small = captured["body"]["max_tokens"]

    app_settings.update({"llm_context_window": 131072})
    llm_client.chat_json(sample_image, long_prompt)
    large = captured["body"]["max_tokens"]

    assert large > small


# --------------------------------------------------------------------------- #
# Connection probe
# --------------------------------------------------------------------------- #

def test_test_connection_reports_success(capture_request, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_MODEL", "vision-model-1")

    captured, reply = capture_request
    reply["payload"] = _envelope("ok")

    result = llm_client.test_connection()

    assert result["ok"] is True
    assert result["model"] == "vision-model-1"
    assert result["reply"] == "ok"
    # The probe must attach an image, because every real feature does. A
    # text-only probe would report success for a model that then fails on
    # every actual call.
    content = captured["body"]["messages"][0]["content"]
    assert isinstance(content, list)
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert captured["body"]["model"] == "vision-model-1"


def test_test_connection_budget_is_large_enough_for_a_reasoning_model(
    capture_request, monkeypatch
):
    """A tiny cap makes a healthy reasoning model report "empty content".

    An earlier version hardcoded ``max_tokens: 16``; a model that thinks before
    answering spent that on its chain of thought and returned no content, so
    the Settings probe reported a false failure.
    """
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "LLM_CONTEXT_WINDOW", 32_768)

    captured, reply = capture_request
    reply["payload"] = _envelope('{"ok": true}')

    llm_client.test_connection()

    assert captured["body"]["max_tokens"] > 16


def test_test_connection_reports_truncation_as_a_budget_problem(monkeypatch):
    """Truncation must not be reported as bad credentials."""
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        return _FakeResponse(
            {
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "length",
                        "message": {"role": "assistant", "content": "", "reasoning_content": "thinking..."},
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    result = llm_client.test_connection()

    assert result["ok"] is False
    assert "budget" in result["error"].lower() or "token" in result["error"].lower()
    assert "api key" not in result["error"].lower()


def test_test_connection_uses_overrides_without_persisting_them(
    capture_request, monkeypatch
):
    """Testing a candidate endpoint must not pin it as the live configuration."""
    from config import settings
    from services import app_settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-env")
    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://env.example/v1")

    captured, reply = capture_request
    reply["payload"] = _envelope("ok")

    result = llm_client.test_connection(
        {"llm_base_url": "https://candidate.example/v1", "llm_model": "candidate-model"}
    )

    assert result["ok"] is True
    # The probe went to the candidate...
    assert captured["url"] == "https://candidate.example/v1/chat/completions"
    assert captured["body"]["model"] == "candidate-model"
    # ...but nothing was written.
    assert app_settings.load_raw() == {}
    assert app_settings.resolve().base_url == "http://env.example/v1"


def test_test_connection_keeps_the_stored_key_when_the_override_is_blank(
    capture_request, monkeypatch
):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-env-key")

    captured, reply = capture_request
    reply["payload"] = _envelope("ok")

    llm_client.test_connection({"llm_api_key": ""})

    assert captured["headers"]["Authorization"] == "Bearer sk-env-key"


def test_test_connection_uses_a_submitted_key(capture_request, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-env-key")

    captured, reply = capture_request
    reply["payload"] = _envelope("ok")

    llm_client.test_connection({"llm_api_key": "sk-candidate-key"})

    assert captured["headers"]["Authorization"] == "Bearer sk-candidate-key"


def test_test_connection_reports_a_missing_key_without_calling_out(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    def explode(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("a request was sent without a key")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", explode)

    result = llm_client.test_connection()

    assert result["ok"] is False
    assert "key" in result["error"].lower()


def test_test_connection_surfaces_an_http_error(monkeypatch):
    import urllib.error

    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", {}, io.BytesIO(b"bad key")
        )

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    result = llm_client.test_connection()

    assert result["ok"] is False
    assert "401" in result["error"]


def test_test_connection_surfaces_a_connection_error(monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def fake_urlopen(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", fake_urlopen)

    result = llm_client.test_connection()

    assert result["ok"] is False
    assert "connection refused" in result["error"]


def test_settings_test_endpoint_returns_the_probe_result(client, monkeypatch):
    """The router must report the probe's verdict, whatever it is."""
    from services import llm_client as client_module

    monkeypatch.setattr(
        client_module,
        "test_connection",
        lambda overrides=None, **kwargs: {"ok": True, "model": "m", "reply": "ok"},
    )

    response = client.post("/api/settings/test", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["model"] == "m"


def test_settings_test_endpoint_returns_a_failure_as_data(client, monkeypatch):
    """A failed probe is a normal UI state, not an HTTP error."""
    from services import llm_client as client_module

    monkeypatch.setattr(
        client_module,
        "test_connection",
        lambda overrides=None, **kwargs: {"ok": False, "error": "HTTP 401: bad key"},
    )

    response = client.post("/api/settings/test", json={})

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "401" in response.json()["error"]


def test_settings_test_endpoint_does_not_persist_the_candidates(client, monkeypatch):
    """A probe must leave the stored configuration untouched."""
    from config import settings
    from services import app_settings
    from services import llm_client as client_module

    monkeypatch.setattr(settings, "LLM_BASE_URL", "http://env.example/v1")
    monkeypatch.setattr(
        client_module, "test_connection", lambda overrides=None, **kwargs: {"ok": True}
    )

    response = client.post(
        "/api/settings/test",
        json={"llm_base_url": "https://probe.example/v1", "llm_model": "probe-model"},
    )

    assert response.status_code == 200
    assert app_settings.load_raw() == {}
    assert client.get("/api/settings").json()["effective_base_url"] == (
        "http://env.example/v1"
    )


def test_settings_test_endpoint_passes_the_candidates_to_the_probe(client, monkeypatch):
    from services import llm_client as client_module

    seen: dict = {}

    def fake_probe(overrides=None, **kwargs):
        seen["overrides"] = overrides
        return {"ok": True}

    monkeypatch.setattr(client_module, "test_connection", fake_probe)

    client.post(
        "/api/settings/test",
        json={"llm_base_url": "https://probe.example/v1", "llm_model": "probe-model"},
    )

    assert seen["overrides"]["llm_base_url"] == "https://probe.example/v1"
    assert seen["overrides"]["llm_model"] == "probe-model"


def test_settings_test_endpoint_rejects_an_invalid_url(client):
    response = client.post("/api/settings/test", json={"llm_base_url": "nope"})

    assert response.status_code == 400


def test_audit_image_returns_contract_fields(capture_request, sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope(
        '{"confidence_score": 0.9, "flags": ["soft focus"], "is_commercially_viable": true}'
    )

    result = gemini_auditor.audit_image(sample_image)

    assert set(result) == {"passed", "confidence_score", "flags", "reason"}
    assert result["passed"] is True
    assert result["confidence_score"] == 0.9
    assert result["flags"] == ["soft focus"]


def test_audit_image_fails_when_not_viable(capture_request, sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    reply["payload"] = _envelope(
        '{"confidence_score": 0.95, "flags": [], "is_commercially_viable": false}'
    )

    result = gemini_auditor.audit_image(sample_image)

    assert result["passed"] is False
    assert "not commercially viable" in result["reason"]


def test_audit_image_degrades_on_gateway_error(sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def boom(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", boom)

    result = gemini_auditor.audit_image(sample_image)

    assert result["passed"] is False
    assert "Semantic audit failed" in result["reason"]


def test_generate_metadata_cleans_and_caps_keywords(
    capture_request, sample_image, monkeypatch
):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    captured, reply = capture_request
    keywords = [f"kw{i}" for i in range(40)] + ["AI", "generative", "stock"]
    reply["payload"] = _envelope(
        json.dumps({"title": "A Title", "description": "Desc", "keywords": keywords})
    )

    meta = gemini_metadata.generate_metadata(sample_image)

    assert meta["title"] == "A Title"
    # 43 keywords are supplied and 3 are banned, so 40 survive - and the list
    # must stay within Adobe's 49-keyword ceiling.
    assert len(meta["keywords"]) == 40
    assert len(meta["keywords"]) <= 49
    for banned in ("ai", "generative", "stock"):
        assert banned not in [k.lower() for k in meta["keywords"]]
    # The category must always resolve to a valid Adobe code.
    assert 1 <= meta["category"] <= 21


def test_generate_metadata_returns_none_on_gateway_error(sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def boom(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", boom)

    assert gemini_metadata.generate_metadata(sample_image) is None
