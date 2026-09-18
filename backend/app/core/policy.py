"""Versioned product and policy contracts owned by Wave 1."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class CheckSeverity(str, Enum):
    HARD = "hard"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class PolicyCheck:
    rule_id: str
    passed: bool
    severity: CheckSeverity
    message: str
    observed_value: str | int | float | None = None
    threshold: str | int | float | None = None


@dataclass(frozen=True)
class PolicyBaseline:
    """Internal baseline; externally sourced values require release verification."""

    version: str = "wave1-baseline-2026-09"
    title_limit: int = 140
    keyword_limit: int = 35
    minimum_megapixels: float = 4.0
    maximum_file_size_mb: float = 45.0
    recommended_megapixels: float = 12.0
    sharpness_warning_threshold: float = 120.0
    policy_verified: bool = False
    policy_source: str | None = None
    policy_verified_on: str | None = None


FORBIDDEN_KEYWORDS = frozenset(
    {"ai", "generative", "stock", "midjourney", "illustration", "image", "nobody", "copyspace"}
)


def validate_metadata(
    title: str,
    keywords: Iterable[str],
    policy: PolicyBaseline,
) -> "MetadataValidationResult":
    normalized_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
    checks: list[PolicyCheck] = []

    checks.append(
        PolicyCheck(
            rule_id="TITLE_LENGTH",
            passed=len(title) <= policy.title_limit,
            severity=CheckSeverity.HARD,
            message="Title must be within the configured character limit.",
            observed_value=len(title),
            threshold=policy.title_limit,
        )
    )
    checks.append(
        PolicyCheck(
            rule_id="KEYWORD_COUNT",
            passed=0 < len(normalized_keywords) <= policy.keyword_limit,
            severity=CheckSeverity.HARD,
            message="Keyword count must be within the configured bounds.",
            observed_value=len(normalized_keywords),
            threshold=policy.keyword_limit,
        )
    )

    forbidden = sorted({keyword.casefold() for keyword in normalized_keywords} & FORBIDDEN_KEYWORDS)
    checks.append(
        PolicyCheck(
            rule_id="FORBIDDEN_KEYWORD",
            passed=not forbidden,
            severity=CheckSeverity.HARD,
            message="Keywords must not contain prohibited or workflow terms.",
            observed_value=", ".join(forbidden) if forbidden else None,
        )
    )

    return MetadataValidationResult(checks=tuple(checks))


@dataclass(frozen=True)
class MetadataValidationResult:
    checks: tuple[PolicyCheck, ...]

    @property
    def hard_failures(self) -> list[str]:
        return [check.rule_id for check in self.checks if check.severity is CheckSeverity.HARD and not check.passed]

    @property
    def passed(self) -> bool:
        return not self.hard_failures
