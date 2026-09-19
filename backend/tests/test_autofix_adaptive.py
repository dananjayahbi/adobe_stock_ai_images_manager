"""Tests for the adaptive (deep-fix) auto-fix engine.

This mode exists because the single-pass fix was *idempotent*: the recipe derives
each strength as a pure function of the measured issue and clamps it, so
re-running it on its own output reproduced the same strengths and the same image.
That is why an earlier run could report "fixed 4 issue types" while the score did
not move by a single point.

These tests pin the three properties that make the new mode trustworthy:

1. escalation genuinely increases the correction strength;
2. the loop never returns an image worse than one it already had; and
3. when it plateaus, it says *why* instead of implying success.
"""

import numpy as np
import pytest
from PIL import Image

from services.acceptance.scorer import AcceptanceConfig, score_image
from services.acceptance.types import CHROMA_FRINGE, EDGE_HALO, Issue, SOFT_FOCUS
from services.autofix import auto_fix_adaptive, auto_fix_image
from services.autofix.targets import (
    DEFAULT_TARGET,
    MAX_TARGET,
    MIN_TARGET,
    TargetProgress,
    clamp_target,
    diagnose_stuck,
    dimensions_from_report,
)
from services.refine.recipe import (
    ABSOLUTE_MAX_STRENGTH,
    MAX_CORRECTION_STRENGTH,
    apply_recipe,
)


@pytest.fixture()
def bad_pixels_jpeg(tmp_path):
    """A large, noisy, fringed frame - plenty of genuinely fixable issues."""
    rng = np.random.default_rng(5)
    height, width = 1600, 2100  # 3.36 MP; tests do not need Adobe's 4 MP floor
    image = np.zeros((height, width, 3), dtype="uint8")
    image[:, :, 0] = np.linspace(30, 255, width, dtype="uint8")[None, :]
    image[:, :, 1] = 190
    image[:, :, 2] = np.linspace(255, 20, height, dtype="uint8")[:, None]
    noisy = np.clip(
        image.astype("int16") + rng.integers(-55, 55, image.shape), 0, 255
    ).astype("uint8")
    path = tmp_path / "bad.jpg"
    with Image.fromarray(noisy, mode="RGB") as im:
        im.save(path, "JPEG", quality=88)
    return path


# --------------------------------------------------------------------------- #
# Escalation: the mechanism that makes repeat passes do anything at all
# --------------------------------------------------------------------------- #

def test_escalation_does_not_change_default_strength():
    """At escalation 1.0 the recipe must behave exactly as before.

    The default cap is what keeps corrections inside Adobe's "no overprocessing"
    guidance, so introducing escalation must not loosen it.
    """
    rng = np.random.default_rng(1)
    image = (rng.random((64, 64, 3)) * 255).astype("uint8")
    issue = Issue(CHROMA_FRINGE, "major", "fringing", 0.30)

    plain = apply_recipe(image, [issue])
    explicit = apply_recipe(image, [issue], escalation=1.0)

    assert [s.strength for s in plain.steps] == [s.strength for s in explicit.steps]


def test_escalation_increases_correction_strength():
    """The core fix: a retry must actually correct harder than the first pass."""
    rng = np.random.default_rng(2)
    image = (rng.random((64, 64, 3)) * 255).astype("uint8")
    issue = Issue(CHROMA_FRINGE, "major", "fringing", 0.30)

    first = apply_recipe(image, [issue], escalation=1.0)
    second = apply_recipe(image, [issue], escalation=1.5)

    assert second.steps[0].strength > first.steps[0].strength


def test_escalation_never_exceeds_the_absolute_cap():
    """However far the loop escalates, the edit must stay exportable."""
    rng = np.random.default_rng(3)
    image = (rng.random((64, 64, 3)) * 255).astype("uint8")
    issues = [
        Issue(CHROMA_FRINGE, "major", "fringing", 0.30),
        Issue(EDGE_HALO, "major", "halo", 0.20),
        Issue(SOFT_FOCUS, "major", "soft", 30.0),
    ]

    outcome = apply_recipe(image, issues, escalation=50.0)

    assert outcome.steps, "expected corrections to be applied"
    for step in outcome.steps:
        assert step.strength <= ABSOLUTE_MAX_STRENGTH + 1e-9, step
    assert ABSOLUTE_MAX_STRENGTH <= 1.0


def test_default_cap_is_still_the_binding_limit():
    """Guards the invariant the docstring claims."""
    assert MAX_CORRECTION_STRENGTH <= ABSOLUTE_MAX_STRENGTH


# --------------------------------------------------------------------------- #
# Target handling
# --------------------------------------------------------------------------- #

def test_clamp_target_defaults_and_bounds():
    assert clamp_target(None) == DEFAULT_TARGET
    assert clamp_target(0.1) == MIN_TARGET
    assert clamp_target(5.0) == MAX_TARGET
    assert clamp_target("not a number") == DEFAULT_TARGET
    assert clamp_target(0.85) == pytest.approx(0.85)


def test_dimensions_expose_fixable_and_manual_codes(bad_pixels_jpeg):
    report = score_image(bad_pixels_jpeg, config=AcceptanceConfig.from_settings())
    dimensions = dimensions_from_report(report)

    assert dimensions, "a scored image must produce dimensions"
    keys = {d.key for d in dimensions}
    assert "technical" in keys and "detail" in keys

    for dim in dimensions:
        # A dimension is either correctable or it is not - never both.
        assert not (set(dim.fixable_codes) & set(dim.manual_codes))
        assert dim.is_fixable == bool(dim.fixable_codes)


def test_progress_reports_unmet_dimensions():
    from services.autofix.targets import DimensionTarget

    progress = TargetProgress(
        target=0.8,
        overall_score=0.6,
        dimensions=[
            DimensionTarget("a", "Fixable", 0.5, 0.3, ["chroma_fringe"], []),
            DimensionTarget("b", "Manual", 0.5, 0.3, [], ["possible_ip"]),
            DimensionTarget("c", "Met", 0.9, 0.4, ["edge_halo"], []),
        ],
    )

    assert [d.key for d in progress.unmet_fixable] == ["a"]
    assert [d.key for d in progress.unmet_manual] == ["b"]
    assert not progress.all_met
    assert progress.blocked_by_manual is False


def test_progress_blocked_by_manual_when_only_manual_remains():
    from services.autofix.targets import DimensionTarget

    progress = TargetProgress(
        target=0.8,
        overall_score=0.7,
        dimensions=[
            DimensionTarget("a", "Met", 0.9, 0.3, ["chroma_fringe"], []),
            DimensionTarget("b", "Manual", 0.5, 0.3, [], ["possible_ip"]),
        ],
    )

    assert progress.unmet_fixable == []
    assert progress.blocked_by_manual is True
    assert not progress.all_met


def test_diagnose_stuck_explains_the_cliff():
    """The explanation must mention the all-or-nothing scoring, not just "failed"."""
    from services.autofix.targets import DimensionTarget

    fixable = DimensionTarget("d", "Detail", 0.0, 0.2, ["chroma_fringe"], [])
    manual = DimensionTarget("m", "Tech", 0.4, 0.3, [], ["low_resolution"])

    fixable_text = diagnose_stuck(fixable)
    manual_text = diagnose_stuck(manual)

    assert "chroma_fringe" in fixable_text
    assert "all-or-nothing" in fixable_text
    assert "manual decision" in manual_text


# --------------------------------------------------------------------------- #
# The loop itself
# --------------------------------------------------------------------------- #

def test_adaptive_run_produces_a_corrected_file_and_a_log(bad_pixels_jpeg, tmp_path):
    result = auto_fix_adaptive(
        bad_pixels_jpeg, tmp_path, "adaptive-1", target=0.8
    )

    assert result.success is True, result.stop_reason
    assert result.output_path is not None
    from pathlib import Path

    assert Path(result.output_path).is_file()
    assert result.log, "an adaptive run must always produce a log"
    assert result.stop_reason, "the loop must state why it stopped"
    assert result.report is not None


def test_adaptive_log_records_setup_passes_and_the_stop_reason(
    bad_pixels_jpeg, tmp_path
):
    result = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "adaptive-2", target=0.8)

    messages = [entry["message"] for entry in result.log]
    assert any("Starting adaptive" in m for m in messages)
    assert any("Target:" in m for m in messages)
    # The stop reason must appear in the log, not only in the result field.
    assert any(m.startswith("Stopped:") for m in messages)

    levels = {entry["level"] for entry in result.log}
    assert "info" in levels
    # Every entry must be serialisable with the documented shape.
    for entry in result.log:
        assert set(entry) == {"level", "message", "pass", "score"}


def test_adaptive_never_returns_a_worse_image(bad_pixels_jpeg, tmp_path):
    """A pass that scores worse must be reverted, not delivered."""
    result = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "adaptive-3", target=0.95)

    assert result.success is True, result.stop_reason
    assert result.final_score >= result.initial_score, (
        "the loop must never hand back an image that scores below its input"
    )


def test_adaptive_reports_target_and_progress(bad_pixels_jpeg, tmp_path):
    result = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "adaptive-4", target=0.75)

    assert result.target == pytest.approx(0.75)
    assert result.progress_before is not None
    assert result.progress_after is not None
    assert result.progress_before.target == pytest.approx(0.75)
    assert result.progress_after.dimensions


def test_adaptive_target_is_clamped(bad_pixels_jpeg, tmp_path):
    result = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "adaptive-5", target=0.01)
    assert result.target == pytest.approx(MIN_TARGET)


def test_adaptive_does_not_claim_fixes_it_did_not_make(bad_pixels_jpeg, tmp_path):
    """`fixed` and `remaining_fixable` must not overlap."""
    result = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "adaptive-6", target=0.9)

    assert not (set(result.fixed) & set(result.remaining_fixable))
    assert not (set(result.fixed) & set(result.manual))


def test_adaptive_missing_file_fails_cleanly(tmp_path):
    result = auto_fix_adaptive(tmp_path / "nope.jpg", tmp_path, "adaptive-7")
    assert result.success is False
    assert "not found" in result.stop_reason.lower()


def test_adaptive_is_at_least_as_good_as_single_pass(bad_pixels_jpeg, tmp_path):
    """The new mode must not regress against the old one on the same input."""
    single = auto_fix_image(bad_pixels_jpeg, tmp_path, "cmp-single")
    adaptive = auto_fix_adaptive(bad_pixels_jpeg, tmp_path, "cmp-adaptive", target=0.8)

    assert adaptive.final_score >= single.final_score - 1e-9
