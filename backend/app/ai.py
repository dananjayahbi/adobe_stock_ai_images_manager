"""Provider-neutral AI contracts, validation, provenance, and bounded retries for Wave 6."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import random
import time
from typing import Any, Callable, Mapping, Protocol
import unicodedata

from app.core.policy import PolicyBaseline


class AiOperation(str, Enum):
    SEMANTIC_AUDIT = "semantic_audit"
    METADATA_GENERATION = "metadata_generation"


class ValidationError(ValueError):
    """Provider output did not satisfy the versioned domain contract."""


class AiProviderError(RuntimeError):
    """Provider failure with an explicit retry classification."""

    def __init__(self, code: str, message: str, *, retryable: bool, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.status = status


@dataclass(frozen=True)
class ProviderRequest:
    operation: AiOperation
    artifact_hash: str
    model: str
    prompt_version: str
    schema_version: str
    policy_version: str
    app_version: str
    provider: str = "gemini"
    sdk_version: str = "unknown"
    temperature: float = 0.0
    response_mode: str = "json"

    def _provenance(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "artifact_hash": self.artifact_hash,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "app_version": self.app_version,
            "provider": self.provider,
            "sdk_version": self.sdk_version,
            "temperature": self.temperature,
            "response_mode": self.response_mode,
        }

    def provenance_json(self) -> str:
        return json.dumps(self._provenance(), sort_keys=True, separators=(",", ":"))

    def deduplication_key(self) -> str:
        return hashlib.sha256(self.provenance_json().encode("utf-8")).hexdigest()


class ProviderAdapter(Protocol):
    def call(self, request: ProviderRequest) -> Mapping[str, Any]: ...


class GeminiProvider:
    """Small SDK-independent adapter; transport is injectable for tests/offline use."""

    def __init__(
        self,
        api_key: str | None,
        *,
        endpoint: str = "https://generativelanguage.googleapis.com/v1beta/models",
        transport: Callable[[str, Mapping[str, str], Mapping[str, Any]], Mapping[str, Any]] | None = None,
        max_payload_bytes: int = 10 * 1024 * 1024,
    ):
        self.api_key = api_key
        self.endpoint = endpoint.rstrip("/")
        self.transport = transport
        self.max_payload_bytes = max_payload_bytes

    def call(self, request: ProviderRequest) -> Mapping[str, Any]:
        if not self.api_key:
            raise AiProviderError("provider-unavailable", "AI provider credentials are not configured", retryable=False)
        if self.transport is None:
            raise AiProviderError("provider-unavailable", "No provider transport is configured", retryable=False)
        body = {
            "contents": [{"parts": [{"text": f"operation={request.operation.value}; artifact={request.artifact_hash}"}]}],
            "generationConfig": {"temperature": request.temperature, "responseMimeType": request.response_mode},
        }
        encoded_size = len(json.dumps(body, separators=(",", ":")).encode("utf-8"))
        if encoded_size > self.max_payload_bytes:
            raise AiProviderError("payload-too-large", "AI request exceeds configured payload limit", retryable=False)
        headers = {"Content-Type": "application/json", "X-Studio-Model": request.model}
        try:
            response = self.transport(f"{self.endpoint}/{request.model}:generateContent", headers, body)
        except AiProviderError:
            raise
        except TimeoutError as error:
            raise AiProviderError("timeout", "AI provider request timed out", retryable=True) from error
        except OSError as error:
            raise AiProviderError("transport", "AI provider transport failed", retryable=True) from error
        if not isinstance(response, Mapping):
            raise AiProviderError("malformed-response", "AI provider returned an invalid envelope", retryable=False)
        if "error" in response:
            error = response["error"] if isinstance(response["error"], Mapping) else {}
            status = int(error.get("code", 0)) or None
            retryable = status in {408, 429, 500, 502, 503, 504}
            raise AiProviderError("provider-error", "AI provider rejected the request", retryable=retryable, status=status)
        return response


@dataclass(frozen=True)
class SemanticFinding:
    category: str
    severity: str
    explanation: str
    confidence: float | None = None
    region: str | None = None


@dataclass(frozen=True)
class SemanticAudit:
    recommendation: str
    confidence: float
    findings: tuple[SemanticFinding, ...]
    uncertainty: str | None
    request: ProviderRequest
    review_required: bool = True


@dataclass(frozen=True)
class MetadataProposal:
    title: str
    keywords: tuple[str, ...]
    language: str
    generation_note: str | None
    removed_values: tuple[str, ...]
    request: ProviderRequest


_ALLOWED_CATEGORIES = {
    "technical-looking-artifact",
    "anatomy",
    "text-or-logo-concern",
    "likeness-concern",
    "composition-concern",
    "unknown",
    # Friendly aliases accepted at the boundary and normalized below.
    "technical_artifact",
    "logo",
    "likeness",
    "composition",
}
_ALLOWED_SEVERITIES = {"informational", "warning", "high-risk", "blocking-candidate"}
_ALLOWED_RECOMMENDATIONS = {"pass", "review", "reject", "uncertain"}


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def _text(value: Any, label: str, *, required: bool = True, limit: int = 1000) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be a string")
    result = unicodedata.normalize("NFC", value).strip()
    if required and not result:
        raise ValidationError(f"{label} must not be empty")
    if len(result) > limit:
        raise ValidationError(f"{label} exceeds its length limit")
    return result


def _confidence(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValidationError(f"{label} must be between 0 and 1")
    return result


def _category(value: Any) -> str:
    category = _text(value, "finding.category", limit=80)
    if category not in _ALLOWED_CATEGORIES:
        raise ValidationError(f"unknown finding category: {category}")
    return {
        "technical_artifact": "technical-looking-artifact",
        "logo": "text-or-logo-concern",
        "likeness": "likeness-concern",
        "composition": "composition-concern",
    }.get(category, category)


def semantic_audit_from_provider(payload: Mapping[str, Any], request: ProviderRequest) -> SemanticAudit:
    data = _mapping(payload, "semantic response")
    recommendation = _text(data.get("recommendation"), "recommendation", limit=30)
    if recommendation not in _ALLOWED_RECOMMENDATIONS:
        raise ValidationError("recommendation is not recognized")
    confidence = _confidence(data.get("confidence"), "confidence")
    raw_findings = data.get("findings")
    if not isinstance(raw_findings, list) or len(raw_findings) > 50:
        raise ValidationError("findings must be a bounded array")
    findings: list[SemanticFinding] = []
    for raw in raw_findings:
        finding = _mapping(raw, "finding")
        severity = _text(finding.get("severity"), "finding.severity", limit=30)
        if severity not in _ALLOWED_SEVERITIES:
            raise ValidationError("finding severity is not recognized")
        finding_confidence = finding.get("confidence")
        findings.append(
            SemanticFinding(
                category=_category(finding.get("category")),
                severity=severity,
                explanation=_text(finding.get("explanation"), "finding.explanation", limit=500),
                confidence=None if finding_confidence is None else _confidence(finding_confidence, "finding.confidence"),
                region=_text(finding.get("region"), "finding.region", required=False, limit=200),
            )
        )
    if recommendation == "pass" and any(f.severity == "blocking-candidate" for f in findings):
        raise ValidationError("pass recommendation contradicts a blocking-candidate finding")
    uncertainty = _text(data.get("uncertainty"), "uncertainty", required=False, limit=500)
    review_required = recommendation != "pass" or bool(findings) or uncertainty is not None
    return SemanticAudit(recommendation, confidence, tuple(findings), uncertainty, request, review_required)


def metadata_from_provider(
    payload: Mapping[str, Any], request: ProviderRequest, policy: PolicyBaseline
) -> MetadataProposal:
    data = _mapping(payload, "metadata response")
    title = _text(data.get("title"), "title", limit=policy.title_limit)
    if any(ord(char) < 32 and char not in "\t" for char in title):
        raise ValidationError("title contains control characters")
    raw_keywords = data.get("keywords")
    if not isinstance(raw_keywords, list) or not raw_keywords:
        raise ValidationError("keywords must be a non-empty array")
    keywords: list[str] = []
    removed: list[str] = []
    seen: set[str] = set()
    forbidden = {"ai", "generative", "stock", "midjourney", "illustration", "image", "nobody", "copyspace"}
    for raw in raw_keywords:
        if not isinstance(raw, str):
            raise ValidationError("keywords must contain strings")
        keyword = unicodedata.normalize("NFC", raw).strip()
        key = keyword.casefold()
        if not keyword or key in seen or key in forbidden:
            if keyword:
                removed.append(keyword)
            continue
        if len(keyword) > 80:
            removed.append(keyword)
            continue
        seen.add(key)
        keywords.append(keyword)
    if not keywords or len(keywords) > policy.keyword_limit:
        raise ValidationError("sanitized keyword count is outside policy bounds")
    language = _text(data.get("language", "en"), "language", limit=20)
    if language != "en":
        raise ValidationError("only English metadata is currently supported")
    return MetadataProposal(
        title=title,
        keywords=tuple(keywords),
        language=language,
        generation_note=_text(data.get("generation_note"), "generation_note", required=False, limit=300),
        removed_values=tuple(removed),
        request=request,
    )


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 10.0
    jitter_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("retry policy bounds are invalid")


@dataclass
class Budget:
    max_calls: int
    calls: int = 0

    def consume(self) -> None:
        if self.calls >= self.max_calls:
            raise AiProviderError("budget-exhausted", "AI call budget exhausted", retryable=False)
        self.calls += 1


def execute_with_retry(
    operation: Callable[[ProviderRequest], Any],
    request: ProviderRequest,
    retry_policy: RetryPolicy,
    budget: Budget,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    random_source: Callable[[], float] = random.random,
) -> Any:
    last_error: AiProviderError | None = None
    for attempt in range(1, retry_policy.max_attempts + 1):
        budget.consume()
        try:
            return operation(request)
        except AiProviderError as error:
            last_error = error
            if not error.retryable or attempt >= retry_policy.max_attempts:
                raise
            delay = min(retry_policy.max_delay_seconds, retry_policy.base_delay_seconds * (2 ** (attempt - 1)))
            if retry_policy.jitter_seconds:
                delay += random_source() * retry_policy.jitter_seconds
            sleeper(delay)
    raise last_error or RuntimeError("retry loop ended without a result")
