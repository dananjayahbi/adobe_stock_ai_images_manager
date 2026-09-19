"""Tests for the auto-fix engine.

The engine exists so the "auto-fixable" badges in the inspection modal lead
somewhere. These tests pin the contract the UI depends on:

* an sRGB issue is genuinely resolved and the output is verified to carry the
  profile (read back from disk, not assumed);
* issues needing a human decision are reported as ``manual`` and never silently
  attempted;
* a fix that improves the score without clearing the threshold is still a
  success, because a corrected file was written.
"""

import numpy as np
import pytest
from PIL import Image

from services.acceptance.types import (
    CHROMA_FRINGE,
    EXCESSIVE_NOISE,
    MANUAL_ONLY_CODES,
    NOT_SRGB,
    OVERALL_OVERSATURATED,
    POSSIBLE_IP,
    SEMANTIC_FLAGGED,
    SOFT_FOCUS,
    Issue,
)
from services.autofix import auto_fix_image, convert_to_srgb, needs_srgb_fix
from services.autofix.engine import _classify, _codes, _worst_severity
from services.srgb_profile import has_srgb_profile


@pytest.fixture()
def oversaturated_jpeg(tmp_path):
    """A saturated colour image with no ICC profile - the sRGB failure case."""
    path = tmp_path / "saturated.jpg"
    height, width = 240, 320
    image = np.zeros((height, width, 3), dtype="uint8")
    # Strong, fully saturated red/green bands drive global saturation up.
    image[:, : width // 2] = (255, 0, 0)
    image[:, width // 2 :] = (0, 255, 0)
    Image.fromarray(image).save(str(path), "JPEG", quality=95)
    return path


def test_needs_srgb_fix_detects_the_code():
    assert needs_srgb_fix([Issue(NOT_SRGB, "major", "no profile")]) is True
    assert needs_srgb_fix([Issue(OVERALL_OVERSATURATED, "minor", "too vivid")]) is False


def test_convert_to_srgb_returns_pixels_for_untagged_file(oversaturated_jpeg):
    conversion = convert_to_srgb(oversaturated_jpeg)
    assert conversion is not None
    assert conversion.transformed is False
    assert conversion.had_foreign_profile is False
    assert conversion.image_rgb.shape[:2] == (240, 320)


def test_convert_to_srgb_handles_undecodable_file(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    assert convert_to_srgb(broken) is None


def test_codes_deduplicates_and_preserves_order():
    issues = [
        Issue(SEMANTIC_FLAGGED, "major", "a"),
        Issue(NOT_SRGB, "major", "b"),
        Issue(SEMANTIC_FLAGGED, "major", "c"),
    ]
    assert _codes(issues) == [SEMANTIC_FLAGGED, NOT_SRGB]


def test_classify_counts_a_severity_reduction_as_fixed():
    """A capped correction can improve a metric without clearing its threshold.

    Reporting that as "not fixed" would be as wrong as claiming it succeeded.
    """
    before = [Issue(CHROMA_FRINGE, "major", "fringing", 0.3)]
    after = [Issue(CHROMA_FRINGE, "minor", "fringing", 0.12)]

    fixed, outstanding = _classify({CHROMA_FRINGE}, before, after)

    assert fixed == [CHROMA_FRINGE]
    assert outstanding == [CHROMA_FRINGE]


def test_classify_does_not_claim_a_persisting_issue():
    """No movement means no claim: same severity must not count as fixed."""
    before = [Issue(EXCESSIVE_NOISE, "major", "grain", 0.9)]
    after = [Issue(EXCESSIVE_NOISE, "major", "grain", 0.89)]

    fixed, outstanding = _classify({EXCESSIVE_NOISE}, before, after)

    assert fixed == []
    assert outstanding == [EXCESSIVE_NOISE]


def test_classify_treats_a_vanished_issue_as_fixed():
    before = [Issue(NOT_SRGB, "major", "no profile")]
    fixed, outstanding = _classify({NOT_SRGB}, before, [])

    assert fixed == [NOT_SRGB]
    assert outstanding == []


def test_worst_severity_keeps_the_most_serious_rank():
    issues = [
        Issue(CHROMA_FRINGE, "minor", "a"),
        Issue(CHROMA_FRINGE, "critical", "b"),
        Issue(SOFT_FOCUS, "major", "c"),
    ]
    ranks = _worst_severity(issues)

    assert ranks[CHROMA_FRINGE] == 0  # critical wins
    assert ranks[SOFT_FOCUS] == 1


def test_auto_fix_never_lists_a_code_as_both_fixed_and_remaining(
    oversaturated_jpeg, tmp_path
):
    """The UI renders these as two separate lists; overlap would be nonsense."""
    result = auto_fix_image(oversaturated_jpeg, tmp_path, "rec-6")

    assert result.success is True, result.reason
    assert not (set(result.fixed) & set(result.remaining_fixable))
    assert not (set(result.fixed) & set(result.manual))


def test_auto_fix_writes_a_corrected_file(oversaturated_jpeg, tmp_path):
    result = auto_fix_image(oversaturated_jpeg, tmp_path, "rec-1")

    assert result.success is True, result.reason
    assert result.output_path is not None
    from pathlib import Path

    assert Path(result.output_path).is_file()
    assert result.report is not None
    # The score must be reported against the file that was actually written.
    assert 0.0 <= result.final_score <= 1.0


def test_auto_fix_output_is_verifiably_srgb(oversaturated_jpeg, tmp_path):
    """Read the profile back from disk - do not trust the writer's return value.

    The Stage 3 upscaler shipped a bug where ``srgb_embedded`` was echoed from
    the request instead of read from the file, so it claimed success while
    writing an untagged JPEG.
    """
    result = auto_fix_image(oversaturated_jpeg, tmp_path, "rec-2")

    assert result.success is True, result.reason
    assert result.srgb_embedded is True
    assert has_srgb_profile(result.output_path) is True


def test_auto_fix_reports_manual_issues_without_attempting_them(
    oversaturated_jpeg, tmp_path
):
    """A suspected logo must be surfaced, never silently "fixed"."""
    semantic = {
        "confidence_score": 0.4,
        "flags": ["Recognizable brand logo on the subject's jacket"],
    }
    result = auto_fix_image(oversaturated_jpeg, tmp_path, "rec-3", semantic=semantic)

    assert result.success is True, result.reason
    # The scorer maps a "logo" flag to possible_ip (critical), not the generic
    # semantic_flagged code - either way it must land in `manual`.
    assert POSSIBLE_IP in result.manual
    # It must not claim to have fixed something it cannot fix.
    assert POSSIBLE_IP not in result.fixed
    assert not (set(result.fixed) & MANUAL_ONLY_CODES)


def test_auto_fix_on_already_passing_image_is_a_no_op(tmp_path, sample_jpeg):
    """A clean image must not be rewritten for no reason."""
    source = sample_jpeg()
    result = auto_fix_image(source, tmp_path, "rec-4")

    if result.initial_passed:
        assert result.success is False
        assert "Already clears" in result.reason
        assert result.output_path is None


def test_auto_fix_missing_file_reports_failure(tmp_path):
    result = auto_fix_image(tmp_path / "nope.jpg", tmp_path, "rec-5")
    assert result.success is False
    assert "not found" in result.reason.lower()


def test_manual_only_codes_are_never_reported_as_fixed():
    """Guards the vocabulary split: manual codes must stay out of every fixer."""
    from services.acceptance.types import AUTOFIXABLE_CODES, REFINABLE_CODES

    assert REFINABLE_CODES & MANUAL_ONLY_CODES == frozenset()
    assert AUTOFIXABLE_CODES & MANUAL_ONLY_CODES == frozenset()
    # The colour profile is a *container* fix, so it must be auto-fixable even
    # though the pixel recipe has no branch for it. Classing it as manual-only
    # told the operator to do by hand what the pipeline can do itself.
    assert NOT_SRGB in AUTOFIXABLE_CODES
    assert NOT_SRGB not in REFINABLE_CODES
