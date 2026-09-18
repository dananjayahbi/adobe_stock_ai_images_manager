"""Tests for the OpenAI-compatible LLM gateway client and its consumers.

Network calls are stubbed so these run offline; the goal is to pin the
request shape and the error/parse handling, not the provider behaviour.
"""

import json

import pytest

from services import gemini_auditor, gemini_metadata, llm_client
from services.llm_client import LLMError


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


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
    assert len(meta["keywords"]) == 35
    for banned in ("ai", "generative", "stock"):
        assert banned not in [k.lower() for k in meta["keywords"]]


def test_generate_metadata_returns_none_on_gateway_error(sample_image, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    def boom(request, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", boom)

    assert gemini_metadata.generate_metadata(sample_image) is None
