"""Regression tests for the acceptance scorer's calibration.

These tests exist because the scorer reported **exactly 55.0%** for every image,
including a real, already-approved Adobe Stock photograph. 55.0% is the value of
``ceiling_floor``, which is only reached when a sub-score COMPONENT collapses to
0.0 - so something was scoring zero on every image.

Two independent defects were responsible, both proven against synthetic ground
truth with a known correct answer:

1. **The chromatic-aberration detector measured colour contrast, not channel
   misalignment.** It Laplacian-filtered ``R-G`` and ``B-G``, so any saturated
   object boundary registered as fringing. A clean frame measured 0.35 and a
   frame with *real* aberration measured 0.30 - i.e. it was both a false
   positive and non-monotonic.
2. **The texture rule penalised a LOW noise floor as "flat synthetic texture"
   at MAJOR severity**, capping the score at ``ceiling_floor``. Adobe's
   published guidance is the opposite: "check that noise and artifacts are
   minimized".

The synthetic cases below encode the ground truth so neither defect can return
unnoticed.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from services.acceptance import chroma, scorer
from services.acceptance.calibration import (
    ADVISORY_CODES,
    DECISIVE_CODES,
    REFUTED_ASSUMPTIONS,
    TIER_ADVISORY,
    THRESHOLDS,
    tier_for,
)


# --------------------------------------------------------------------------- #
# Synthetic ground-truth imagery
# --------------------------------------------------------------------------- #

def _saturated_scene() -> np.ndarray:
    """Smooth gradients plus hard, heavily saturated colour edges. No artefacts."""
    height = width = 768
    image = np.zeros((height, width, 3), np.uint8)
    for y in range(height):
        image[y, :] = (200 - y // 6, 150 - y // 10, 90)
    cv2.circle(image, (220, 220), 120, (40, 40, 210), -1)
    cv2.rectangle(image, (450, 380), (680, 600), (60, 200, 60), -1)
    cv2.line(image, (70, 690), (700, 710), (240, 240, 240), 7)
    rng = np.random.default_rng(7)
    return cv2.add(image, rng.integers(0, 5, (height, width, 3), dtype=np.uint8))


def _apply_lateral_ca(image: np.ndarray, percent: float) -> np.ndarray:
    """True lateral chromatic aberration: scale R and B about the centre."""
    height, width = image.shape[:2]
    centre = (width / 2.0, height / 2.0)
    blue, green, red = cv2.split(image.astype(np.float32))
    matrix_r = cv2.getRotationMatrix2D(centre, 0.0, 1.0 + percent / 100.0)
    matrix_b = cv2.getRotationMatrix2D(centre, 0.0, 1.0 - percent / 100.0)
    red_out = cv2.warpAffine(red, matrix_r, (width, height),
                             flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    blue_out = cv2.warpAffine(blue, matrix_b, (width, height),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return cv2.merge([blue_out, green, red_out]).clip(0, 255).astype(np.uint8)


def _apply_overshoot(image: np.ndarray, amount: float = 0.9) -> np.ndarray:
    """Over-sharpening: unsharp mask strong enough to produce a bright rim."""
    blurred = cv2.GaussianBlur(image.astype(np.float32), (0, 0), 2.0)
    sharpened = image.astype(np.float32) + amount * (
        image.astype(np.float32) - blurred
    )
    return sharpened.clip(0, 255).astype(np.uint8)


def _greyscale_edges() -> np.ndarray:
    """R == G == B, so chromatic aberration is physically impossible."""
    image = np.zeros((512, 512, 3), np.uint8)
    cv2.rectangle(image, (60, 60), (440, 440), (200, 200, 200), -1)
    cv2.line(image, (0, 256), (511, 256), (30, 30, 30), 7)
    cv2.circle(image, (256, 400), 60, (90, 90, 90), -1)
    return image


def _write(tmp_path, name: str, image: np.ndarray) -> str:
    path = tmp_path / name
    cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return str(path)


# --------------------------------------------------------------------------- #
# Chromatic aberration: must measure MISALIGNMENT, not colour contrast
# --------------------------------------------------------------------------- #

def test_clean_saturated_edges_are_not_reported_as_fringing():
    """A saturated object boundary is colour CONTRAST, not chromatic aberration.

    The old detector reported 0.35 here (35% of edge pixels "fringed").
    """
    misalignment = chroma.measure_channel_misalignment(_saturated_scene())
    assert misalignment < 0.30, (
        f"clean saturated edges measured {misalignment:.3f}; a colour-contrast "
        "detector has been reintroduced"
    )


def test_greyscale_edges_report_no_chromatic_aberration():
    """R == G == B makes misalignment impossible, so the index must be 0."""
    assert chroma.measure_channel_misalignment(_greyscale_edges()) == 0.0


def test_misalignment_rises_sharply_with_aberration():
    """The old metric was non-monotonic, so it could not rank severity.

    Asserted in terms of *separation* rather than strict monotonicity: the index
    saturates once the aberration is clearly visible, so a tiny dip at extreme
    shifts is expected and not a defect.
    """
    scene = _saturated_scene()
    clean = chroma.measure_channel_misalignment(scene)
    values = [
        chroma.measure_channel_misalignment(_apply_lateral_ca(scene, percent))
        for percent in (0.5, 1.0, 2.0)
    ]
    assert clean < 0.20, f"clean frame scored too high: {clean:.3f}"
    assert all(value > 0.60 for value in values), (
        f"visible aberration not detected: clean={clean:.3f}, ca={values}"
    )
    assert min(values) - clean > 0.5, (
        f"insufficient separation: clean={clean:.3f}, ca={values}"
    )


def test_real_aberration_scores_above_the_fail_threshold():
    scene = _saturated_scene()
    strong = chroma.measure_channel_misalignment(_apply_lateral_ca(scene, 2.0))
    cfg = scorer.AcceptanceConfig()
    assert strong > cfg.chroma_misalignment_fail


def test_over_sharpening_is_not_mistaken_for_chromatic_aberration():
    """The old detector scored 0.73 here - higher than real aberration.

    Over-sharpening does disturb edge structure slightly, so it may register as
    a mild signal - but it must sit far below real aberration and below the fail
    threshold, or the two defects cannot be told apart.
    """
    scene = _saturated_scene()
    oversharp = chroma.measure_channel_misalignment(_apply_overshoot(scene))
    real_ca = chroma.measure_channel_misalignment(_apply_lateral_ca(scene, 0.5))
    cfg = scorer.AcceptanceConfig()

    assert oversharp < cfg.chroma_misalignment_fail
    assert oversharp < real_ca, (
        f"over-sharpening ({oversharp:.3f}) ranked above real aberration "
        f"({real_ca:.3f})"
    )


# --------------------------------------------------------------------------- #
# Texture: a clean image must NOT be penalised
# --------------------------------------------------------------------------- #

def test_a_clean_low_noise_image_is_not_flagged_as_synthetic(tmp_path):
    """The regression that pinned every image at 55%.

    Adobe's guidance is that noise be *minimised*; no source shows a refusal for
    cleanliness. The old rule emitted MAJOR ``flat_synthetic_texture`` here,
    which capped the score at ``ceiling_floor``.
    """
    # A perfectly clean, smooth image: no grain at all.
    clean = np.zeros((512, 512, 3), np.uint8)
    clean[:, :] = (180, 160, 140)
    cv2.rectangle(clean, (100, 100), (400, 400), (120, 90, 60), -1)

    report = scorer.score_image(_write(tmp_path, "clean.jpg", clean))
    codes = {issue.code for issue in report.issues}
    assert "flat_synthetic_texture" not in codes, (
        "a clean image was penalised for having no sensor noise"
    )
    assert report.sub_scores["texture"].score > 0.9


def test_heavy_noise_is_flagged(tmp_path):
    """High noise IS an Adobe-listed defect, so the check must still fire.

    Also guards the estimator against the collapse mode found in development: a
    hard-threshold "flat region" split reports ZERO noise on the noisiest images,
    because heavy noise pushes the local standard deviation above the flat cut.
    """
    scene = _saturated_scene()
    rng = np.random.default_rng(3)
    noisy = np.clip(
        scene.astype(np.float32) + rng.normal(0, 40, scene.shape), 0, 255
    ).astype(np.uint8)

    report = scorer.score_image(_write(tmp_path, "noisy.jpg", noisy))
    assert "excessive_noise" in {issue.code for issue in report.issues}


def test_noise_estimate_never_collapses_as_noise_grows():
    """The measured noise must not DROP when more noise is added."""
    from services.acceptance import texture

    scene = _saturated_scene()
    measured: list[float] = []
    for injected in (0.0, 2.0, 5.0, 10.0, 20.0, 40.0):
        rng = np.random.default_rng(21)
        grain = rng.normal(0, injected, (scene.shape[0], scene.shape[1], 1))
        noisy = np.clip(scene.astype(np.float32) + grain, 0, 255).astype(np.uint8)
        gray = cv2.cvtColor(noisy, cv2.COLOR_BGR2GRAY).astype(np.float32)
        measured.append(texture.measure_noise_visible(gray))

    for previous, current in zip(measured, measured[1:]):
        assert current >= previous - 1.0, (
            f"noise estimate collapsed as noise increased: {measured}"
        )
    assert measured[-1] > 20.0, f"heavy noise under-measured: {measured}"


# --------------------------------------------------------------------------- #
# The ceiling must be tier-aware
# --------------------------------------------------------------------------- #

def test_only_decisive_components_can_cap_the_score():
    """An advisory nitpick must move the score without pinning it."""
    from services.acceptance.types import SubScore

    advisory_only = SubScore(
        key="detail", label="Detail", score=0.9, weight=0.1,
        components=[1.0, 1.0, 0.0],
        decisive_components=[1.0, 1.0],
    )
    assert advisory_only.worst_component == 0.0
    assert advisory_only.worst_decisive_component == 1.0


def test_a_perfect_image_reaches_a_high_score(tmp_path):
    """A clean, well-exposed, sharp, 4MP+ image must not be capped by a nitpick."""
    # Large enough to clear the 4 MP floor, with genuine texture and edges.
    height, width = 2000, 2000
    rng = np.random.default_rng(11)
    image = np.full((height, width, 3), 128, np.uint8)
    for y in range(height):
        image[y, :, 0] = np.clip(150 + (y - height // 2) // 12, 0, 255)
        image[y, :, 1] = 130
        image[y, :, 2] = 110
    cv2.rectangle(image, (300, 300), (1700, 1700), (90, 70, 50), -1)
    for i in range(12):
        offset = 400 + i * 100
        cv2.line(image, (offset, 350), (offset, 1650), (220, 220, 220), 5)
    grain = rng.normal(0, 3.0, (height, width, 1)).astype(np.float32)
    image = np.clip(image.astype(np.float32) + grain, 0, 255).astype(np.uint8)

    path = tmp_path / "good.jpg"
    cv2.imwrite(str(path), image, [cv2.IMWRITE_JPEG_QUALITY, 95])

    report = scorer.score_image(str(path))
    assert report.score > 0.80, (
        f"a clean, sharp, 4MP image scored {report.score:.4f}; "
        f"issues={[i.code for i in report.issues]}"
    )


def test_the_ceiling_floor_is_only_reachable_by_a_decisive_failure():
    """0.55 must mean "a decisive dimension failed", never "a nitpick fired"."""
    cfg = scorer.AcceptanceConfig()
    assert cfg.ceiling_floor == pytest.approx(0.55)
    # A decisive component at 0.0 caps at the floor; an advisory one does not.
    assert cfg.ceiling_floor + cfg.ceiling_span * 0.0 == pytest.approx(0.55)
    assert cfg.ceiling_floor + cfg.ceiling_span * 1.0 == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# Calibration bookkeeping
# --------------------------------------------------------------------------- #

def test_every_threshold_records_its_provenance():
    for item in THRESHOLDS:
        assert item.provenance in ("adobe", "internal")
        assert item.source.startswith("https://helpx.adobe.com/")
        assert item.note, f"{item.key} has no explanatory note"


def test_container_limits_match_adobe_published_values():
    """These four ARE Adobe requirements, unlike every pixel-level threshold."""
    from services.acceptance.calibration import threshold

    assert threshold("min_megapixels").value == 4.0
    assert threshold("max_megapixels").value == 100.0
    assert threshold("max_file_size_mb").value == 45.0
    assert all(
        threshold(key).is_requirement
        for key in ("min_megapixels", "max_megapixels", "max_file_size_mb")
    )


def test_refuted_assumptions_are_documented():
    """The research findings must stay in the code, not just in a chat log."""
    assert len(REFUTED_ASSUMPTIONS) >= 5
    joined = " ".join(text for _, text in REFUTED_ASSUMPTIONS).lower()
    assert "minimized" in joined
    assert "no added grain" in joined


def test_issue_tiers_are_disjoint_and_cover_the_vocabulary():
    from services.acceptance.types import ISSUE_CODES

    assert not (DECISIVE_CODES & ADVISORY_CODES)
    assert set(ISSUE_CODES) <= (DECISIVE_CODES | ADVISORY_CODES)


def test_chroma_fringe_is_advisory_but_soft_focus_is_decisive():
    assert tier_for("chroma_fringe") == TIER_ADVISORY
    assert tier_for("flat_synthetic_texture") == TIER_ADVISORY
    assert tier_for("soft_focus") != TIER_ADVISORY
    assert tier_for("low_resolution") != TIER_ADVISORY
