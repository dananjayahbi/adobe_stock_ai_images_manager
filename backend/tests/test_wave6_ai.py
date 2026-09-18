from pathlib import Path

import pytest

from app.ai import (
    AiOperation,
    AiProviderError,
    Budget,
    MetadataProposal,
    ProviderRequest,
    RetryPolicy,
    SemanticAudit,
    ValidationError,
    execute_with_retry,
    metadata_from_provider,
    semantic_audit_from_provider,
)
from app.core.policy import PolicyBaseline


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def call(self, request: ProviderRequest):
        self.calls += 1
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def request(operation=AiOperation.SEMANTIC_AUDIT):
    return ProviderRequest(
        operation=operation,
        artifact_hash="a" * 64,
        model="gemini-test",
        prompt_version="semantic-v1",
        schema_version="wave6-v1",
        policy_version="wave1-baseline-2026-09",
        app_version="test",
    )


def test_semantic_response_is_typed_and_bounded():
    result = semantic_audit_from_provider(
        {
            "recommendation": "review",
            "confidence": 0.75,
            "findings": [
                {"category": "anatomy", "severity": "warning", "explanation": "Inspect hand."}
            ],
            "uncertainty": "Model cannot certify rights.",
        },
        request(),
    )

    assert isinstance(result, SemanticAudit)
    assert result.findings[0].category == "anatomy"
    assert result.review_required is True


def test_semantic_contradiction_and_bad_confidence_are_rejected():
    with pytest.raises(ValidationError):
        semantic_audit_from_provider(
            {"recommendation": "pass", "confidence": 1.5, "findings": []}, request()
        )

    with pytest.raises(ValidationError):
        semantic_audit_from_provider(
            {
                "recommendation": "pass",
                "confidence": 0.9,
                "findings": [{"category": "logo", "severity": "blocking-candidate", "explanation": "mark"}],
            },
            request(),
        )


def test_metadata_is_sanitized_deterministically_without_inventing_values():
    result = metadata_from_provider(
        {
            "title": "  Bright city garden  ",
            "keywords": ["Garden", "garden", "AI", " city ", "city", ""],
            "language": "en",
        },
        request(AiOperation.METADATA_GENERATION),
        PolicyBaseline(),
    )

    assert isinstance(result, MetadataProposal)
    assert result.title == "Bright city garden"
    assert result.keywords == ("Garden", "city")
    assert "AI" in result.removed_values


def test_provider_failures_retry_only_when_transient_and_budget_is_bounded():
    provider = FakeProvider([AiProviderError("timeout", "timeout", retryable=True), {"ok": True}])
    attempts = []
    result = execute_with_retry(
        provider.call,
        request(),
        RetryPolicy(max_attempts=3, base_delay_seconds=0),
        Budget(max_calls=2),
        sleeper=lambda delay: attempts.append(delay),
    )

    assert result == {"ok": True}
    assert provider.calls == 2
    assert attempts == [0]

    terminal = FakeProvider([AiProviderError("bad-auth", "auth", retryable=False)])
    with pytest.raises(AiProviderError):
        execute_with_retry(terminal.call, request(), RetryPolicy(max_attempts=3), Budget(max_calls=3))
    assert terminal.calls == 1


def test_provenance_key_excludes_secrets_and_changes_with_context():
    first = request()
    second = ProviderRequest(**{**first.__dict__, "model": "other-model"})
    assert first.deduplication_key() != second.deduplication_key()
    assert "secret" not in first.provenance_json().lower()
