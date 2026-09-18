from app.core.policy import (
    CheckSeverity,
    MetadataValidationResult,
    PolicyBaseline,
    validate_metadata,
)


def test_metadata_policy_rejects_overlong_title_and_forbidden_keywords():
    policy = PolicyBaseline(title_limit=10, keyword_limit=3)

    result = validate_metadata(
        "A descriptive title that is too long",
        ["cat", "AI", "blue", "extra"],
        policy,
    )

    assert isinstance(result, MetadataValidationResult)
    assert result.passed is False
    assert result.hard_failures == ["TITLE_LENGTH", "KEYWORD_COUNT", "FORBIDDEN_KEYWORD"]
    assert result.checks[0].severity is CheckSeverity.HARD


def test_metadata_policy_accepts_truthful_bounded_metadata():
    policy = PolicyBaseline(title_limit=60, keyword_limit=3)

    result = validate_metadata(
        "Blue cat portrait",
        ["cat", "blue", "portrait"],
        policy,
    )

    assert result.passed is True
    assert result.hard_failures == []
    assert all(check.passed for check in result.checks)


def test_ready_requires_human_approval():
    from app.core.workflow import AssetStatus, InvalidTransition, transition

    assert transition(AssetStatus.APPROVED, AssetStatus.FINALIZING, actor="local operator") is AssetStatus.FINALIZING
    assert transition(AssetStatus.FINALIZING, AssetStatus.READY, actor="local operator") is AssetStatus.READY

    try:
        transition(AssetStatus.PASSED, AssetStatus.READY, actor="local operator")
    except InvalidTransition:
        pass
    else:
        raise AssertionError("PASSED must not bypass human approval")
