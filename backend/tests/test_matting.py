"""Tests for the stock-grade cut-out pipeline (services.matting).

Everything here works on in-memory numpy arrays — no rembg, no model, no
network — because each stage is a pure function by design. The synthetic
fixtures mirror the three failure modes Adobe flags: a stair-stepped contour,
a backdrop still bleeding into the soft edge, and stray alpha dust.
"""

from __future__ import annotations

import numpy as np
import pytest

from services.matting import (
    DEFAULT_CONFIG,
    audit,
    build_trimap,
    contour_jaggedness,
    decontaminate,
    dual_matte_report,
    refine_alpha,
    refine_cutout,
    resolve_config,
    sanitize_alpha,
)
from services.matting.defringe import estimate_background
from services.matting.trimap import unknown_fraction

H, W = 240, 320
FG = np.array([40.0, 90.0, 160.0])
BG = np.array([235.0, 225.0, 210.0])


def _grid():
    yy, xx = np.mgrid[0:H, 0:W]
    return yy, xx


def disk_alpha(radius: float = 80.0, feather: float = 1.0) -> np.ndarray:
    """Antialiased disk alpha in 0-255."""
    yy, xx = _grid()
    dist = np.sqrt((xx - W / 2) ** 2 + (yy - H / 2) ** 2)
    return np.clip((radius - dist) / max(feather, 1e-6) + 0.5, 0, 1) * 255.0


def mixed_rgba(alpha: np.ndarray, backdrop: np.ndarray | None = None) -> np.ndarray:
    """A photographic capture: every pixel is a*F + (1-a)*B."""
    back = BG if backdrop is None else backdrop
    a = (alpha / 255.0)[..., None]
    rgb = a * FG[None, None, :] + (1.0 - a) * back[None, None, :]
    return np.dstack([np.clip(rgb, 0, 255), alpha]).astype(np.uint8)


# --------------------------------------------------------------------------- #
# Trimap
# --------------------------------------------------------------------------- #

class TestTrimap:
    def test_three_regions_and_band_width(self):
        trimap = build_trimap(disk_alpha(), radius=6)
        values = set(np.unique(trimap))
        assert values == {0, 128, 255}
        # The unknown band lives only around the boundary.
        assert unknown_fraction(trimap) < 0.15
        solid = np.argwhere(trimap == 255)
        core = np.argwhere(disk_alpha() == 255)
        assert solid.shape[0] < core.shape[0]  # eroded inward

    def test_empty_mask_is_all_background(self):
        assert build_trimap(np.zeros((32, 32))).max() == 0

    def test_full_mask_is_all_foreground(self):
        assert build_trimap(np.full((32, 32), 255.0)).min() == 255

    def test_wider_radius_widens_the_unknown_band(self):
        narrow = unknown_fraction(build_trimap(disk_alpha(), radius=2))
        wide = unknown_fraction(build_trimap(disk_alpha(), radius=10))
        assert wide > narrow


# --------------------------------------------------------------------------- #
# Refinement
# --------------------------------------------------------------------------- #

class TestRefineAlpha:
    def test_tighten_ramp_keeps_endpoints_and_the_crossing(self):
        from services.matting.refine import tighten_ramp

        ramp = np.linspace(0.0, 1.0, 101)
        out = tighten_ramp(ramp, 0.25)
        assert out[0] == 0.0 and out[-1] == 1.0
        assert out[50] == pytest.approx(0.5)  # the 0.5 crossing does not move
        assert np.all(np.diff(out) >= 0)  # monotone: no new contour wobble
        # Everything outside the ramp window is snapped, not softened.
        assert out[10] == 0.0 and out[90] == 1.0

    def test_tighten_ramp_zero_is_a_no_op(self):
        from services.matting.refine import tighten_ramp

        ramp = np.linspace(0.0, 1.0, 51)
        np.testing.assert_array_equal(tighten_ramp(ramp, 0.0), ramp)

    def test_off_returns_the_mask_untouched(self):
        alpha = disk_alpha()
        out, note = refine_alpha(np.zeros((H, W, 3), np.uint8), alpha, method="off")
        assert note == "off"
        np.testing.assert_array_equal(out, alpha)

    def test_unknown_method_falls_back_to_guided(self):
        alpha = disk_alpha()
        out, note = refine_alpha(np.full((H, W, 3), 128, np.uint8), alpha, method="nope")
        assert note == "guided"

    def test_guided_refinement_smoothes_a_stair_stepped_contour(self):
        rng = np.random.default_rng(11)
        soft = np.clip(disk_alpha(radius=80, feather=4), 0, 255)
        noisy = np.clip(soft + rng.normal(0, 75, (H, W)), 0, 255)
        noisy[soft >= 255] = 255
        noisy[soft <= 0] = 0

        before = contour_jaggedness(noisy)
        refined, note = refine_alpha(
            np.full((H, W, 3), 120, np.uint8), noisy, method="guided", trimap_radius=8
        )
        after = contour_jaggedness(refined)

        assert note == "guided"
        assert before > 0.15, "the fixture must actually be jagged"
        assert after < before / 2, f"expected a smoother contour, got {before} -> {after}"

    def test_only_the_unknown_band_is_rewritten(self):
        alpha = disk_alpha()
        guide = np.full((H, W, 3), 90, np.uint8)
        refined, _ = refine_alpha(guide, alpha)

        trimap = build_trimap(alpha, 4)
        assert (trimap == 255).any() and (trimap == 0).any() and (trimap == 128).any()
        # Everything the refiner was not asked to solve is left exactly as it was.
        assert (refined[trimap == 255] == 255).all()
        assert (refined[trimap == 0] == 0).all()


# --------------------------------------------------------------------------- #
# Defringe
# --------------------------------------------------------------------------- #

class TestDecontaminate:
    def test_recovers_pure_foreground_from_a_mixture(self):
        alpha = disk_alpha()
        rgba = mixed_rgba(alpha)
        out, notes = decontaminate(rgba)

        assert notes["applied"] is True
        assert notes["pixels"] > 0
        a = out[..., 3].astype(np.float64)
        band = (a > 16) & (a < 250)
        # The soft edge should now read as the object's own colour.
        error = np.abs(out[band][:, :3].astype(np.float64) - FG[None, :]).mean()
        assert error < 6.0, f"edge colour still carries the backdrop ({error:.1f})"

    def test_is_a_no_op_on_an_already_pure_edge(self):
        alpha = disk_alpha()
        pure = np.dstack([np.broadcast_to(FG, (H, W, 3)), alpha]).astype(np.uint8)
        out, notes = decontaminate(pure)
        assert notes["applied"] is True
        assert notes["max_shift"] <= 1.0

    def test_disabled_by_strength_zero(self):
        out, notes = decontaminate(mixed_rgba(disk_alpha()), strength=0.0)
        assert notes["applied"] is False
        assert notes["reason"] == "disabled"

    def test_refuses_when_there_is_no_transparent_surround(self):
        # A soft edge exists, but nothing in frame is actually transparent, so
        # there is no backdrop colour to un-blend against.
        alpha = np.full((H, W), 255.0)
        alpha[:, 30:70] = np.linspace(200.0, 254.0, 40)[None, :]
        rgba = np.dstack(
            [np.broadcast_to(BG, (H, W, 3)), alpha]
        ).astype(np.uint8)

        _, notes = decontaminate(rgba)
        assert notes["applied"] is False
        assert "transparent surround" in notes["reason"]

    def test_estimate_background_reads_the_surround_colour(self):
        rgba = mixed_rgba(disk_alpha())
        colour, notes = estimate_background(rgba[..., :3], rgba[..., 3].astype(np.float64))
        assert colour is not None
        assert notes["exterior_px"] > 1000
        np.testing.assert_allclose(colour, BG, atol=12.0)


# --------------------------------------------------------------------------- #
# Sanitize
# --------------------------------------------------------------------------- #

class TestSanitize:
    def test_hard_cutoff_kills_sub_threshold_alpha(self):
        alpha = np.zeros((64, 64), np.float64)
        alpha[10:20, 10:20] = 5.0
        alpha[30:50, 30:50] = 255.0
        rgba = np.dstack([np.zeros((64, 64, 3)), alpha]).astype(np.uint8)

        out, stats = sanitize_alpha(rgba, choke_px=0.0, hard_cutoff=8, min_island_px=0)
        assert out[10, 10, 3] == 0
        assert out[35, 35, 3] == 255
        assert stats["hard_cutoff"] == 8

    def test_stray_islands_are_removed_but_connected_parts_are_not(self):
        alpha = np.zeros((80, 80), np.float64)
        alpha[5:60, 5:60] = 255.0          # the subject
        alpha[70:74, 70:74] = 255.0        # 16px dust island
        rgba = np.dstack([np.zeros((80, 80, 3)), alpha]).astype(np.uint8)

        out, stats = sanitize_alpha(rgba, choke_px=0.0, hard_cutoff=8, min_island_px=40)
        assert stats["islands_removed"] == 1
        assert stats["island_pixels"] == 16
        assert out[71, 71, 3] == 0
        assert out[30, 30, 3] == 255  # the subject survives

    def test_choke_pulls_the_edge_inward(self):
        alpha = disk_alpha(radius=80, feather=6)
        rgba = np.dstack([np.zeros((H, W, 3)), alpha]).astype(np.uint8)
        out, stats = sanitize_alpha(rgba, choke_px=1.0, hard_cutoff=0, min_island_px=0)
        assert stats["choke_px"] == 1.0
        assert out[..., 3].sum() < rgba[..., 3].sum()
        assert (out[..., 3] <= rgba[..., 3]).all()

    def test_fractional_choke_is_between_no_choke_and_a_full_pixel(self):
        alpha = disk_alpha(radius=80, feather=6)
        rgba = np.dstack([np.zeros((H, W, 3)), alpha]).astype(np.uint8)
        base = int(rgba[..., 3].sum())
        half, _ = sanitize_alpha(rgba, choke_px=0.5, hard_cutoff=0, min_island_px=0)
        full, _ = sanitize_alpha(rgba, choke_px=1.0, hard_cutoff=0, min_island_px=0)
        assert int(half[..., 3].sum()) < base
        assert int(full[..., 3].sum()) < int(half[..., 3].sum())


# --------------------------------------------------------------------------- #
# Dual-matte QC
# --------------------------------------------------------------------------- #

class TestDualMatteQc:
    def test_clean_geometry_is_not_flagged_as_jagged(self):
        report = dual_matte_report(mixed_rgba(disk_alpha()))
        assert report.band_px > 0
        assert report.contour_jaggedness < 0.15

    def test_a_stair_stepped_contour_is_flagged(self):
        rng = np.random.default_rng(3)
        soft = np.clip(disk_alpha(radius=80, feather=4), 0, 255)
        noisy = np.clip(soft + rng.normal(0, 75, (H, W)), 0, 255)
        noisy[soft >= 255] = 255
        noisy[soft <= 0] = 0
        report = dual_matte_report(
            np.dstack([np.broadcast_to(FG, (H, W, 3)), noisy]).astype(np.uint8)
        )
        assert report.contour_jaggedness >= 0.15
        assert report.verdict in {"warn", "fail"}
        assert any("contour" in issue.lower() for issue in report.issues)

    def test_a_raw_mixture_reports_a_black_canvas_halo(self):
        # A geometrically perfect mask of an *undecontaminated* capture: every
        # soft-edge pixel still carries the backdrop's light.
        report = dual_matte_report(mixed_rgba(disk_alpha()))
        assert report.halo_black > 0.16
        assert report.halo_white < 0.16
        assert report.exposed_on in {"black", "both"}
        assert report.verdict in {"warn", "fail"}

    def test_decontamination_clears_that_finding(self):
        fixed, _ = decontaminate(mixed_rgba(disk_alpha()))
        report = dual_matte_report(fixed)
        assert report.halo_black < 0.16
        assert report.exposed_on == "none"

    def test_hardening_improves_the_overall_audit(self, tmp_path):
        from PIL import Image

        raw = mixed_rgba(disk_alpha(radius=80, feather=3))
        order = {"pass": 0, "warn": 1, "fail": 2}

        raw_path = tmp_path / "raw.png"
        Image.fromarray(raw, "RGBA").save(raw_path)
        hardened, _ = refine_cutout(raw)
        fixed_path = tmp_path / "fixed.png"
        Image.fromarray(hardened, "RGBA").save(fixed_path)

        before, after = audit(raw_path), audit(fixed_path)
        assert order[after["verdict"]] <= order[before["verdict"]]
        assert after["dual_matte"]["halo_black"] < before["dual_matte"]["halo_black"]
        assert after["dual_matte"]["contour_jaggedness"] <= before["dual_matte"][
            "contour_jaggedness"
        ]

    def test_empty_cut_out_fails(self):
        report = dual_matte_report(np.zeros((H, W, 4), np.uint8))
        assert report.verdict == "fail"
        assert "empty" in " ".join(report.issues).lower()

    def test_audit_returns_the_edge_quality_contract_plus_dual_matte(self, tmp_path):
        from PIL import Image

        path = tmp_path / "cutout.png"
        Image.fromarray(mixed_rgba(disk_alpha()), "RGBA").save(path)

        payload = audit(path)
        assert {"coverage", "fringe_px", "jaggedness", "halo"} <= set(payload)
        assert payload["verdict"] in {"pass", "warn", "fail"}
        assert isinstance(payload["issues"], list)
        assert {"contour_jaggedness", "halo_black", "halo_white", "exposed_on"} <= set(
            payload["dual_matte"]
        )

    def test_audit_never_raises_on_a_broken_file(self, tmp_path):
        path = tmp_path / "not-an-image.png"
        path.write_bytes(b"this is not a png")
        payload = audit(path)
        assert payload["verdict"] == "fail"
        assert payload["issues"]


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

class TestPipeline:
    def test_resolve_config_upgrades_a_pre_matting_profile(self):
        # A profile saved before matting existed carries only model/edge_check;
        # those are read by the runner, and every matting knob gets a default.
        merged = resolve_config({"model": "u2net", "edge_check": True})
        assert merged["matting"] == DEFAULT_CONFIG["matting"]
        assert merged["defringe"] is True
        assert merged["sanitize"] is True
        assert merged["trimap_radius"] == DEFAULT_CONFIG["trimap_radius"]

    def test_resolve_config_rejects_an_unknown_matting_method(self):
        assert resolve_config({"matting": "vibes"})["matting"] == "guided"

    def test_unknown_keys_from_an_old_profile_are_ignored(self):
        assert "not_a_key" not in resolve_config({"not_a_key": 1})

    def test_end_to_end_hardens_a_raw_segmentation(self):
        rng = np.random.default_rng(5)
        clean = disk_alpha(radius=80, feather=4)
        noisy = np.clip(clean + rng.normal(0, 60, (H, W)), 0, 255)
        noisy[clean >= 255] = 255
        noisy[clean <= 0] = 0
        # The photo has a smooth edge; only the *mask* is jagged. Feeding a
        # jagged colour field to an edge-aware refiner would just reproduce it.
        photo = mixed_rgba(clean)[..., :3]
        rgba = np.dstack([photo, noisy]).astype(np.uint8)
        rgba[20:24, 20:24, 3] = 255  # stray dust island

        assert contour_jaggedness(noisy) > 0.15, "fixture must start jagged"
        out, stages = refine_cutout(rgba)

        assert out.shape == rgba.shape and out.dtype == np.uint8
        assert stages["matting"]["method"] == "guided"
        assert stages["defringe"]["applied"] is True
        sanitize = stages["sanitize"]
        removed = sanitize["islands_removed"] + sanitize["islands_removed_pre_matting"]
        assert removed >= 1
        assert dual_matte_report(out).verdict in {"pass", "warn"}
        assert contour_jaggedness(out[..., 3]) < 0.15

    def test_every_stage_can_be_switched_off(self):
        rgba = mixed_rgba(disk_alpha())
        out, stages = refine_cutout(
            rgba, {"matting": "off", "defringe": False, "sanitize": False}
        )
        assert stages["matting"]["detail"] == "off"
        assert stages["defringe"]["reason"] == "disabled"
        assert stages["sanitize"]["reason"] == "disabled"
        np.testing.assert_array_equal(out, rgba)

    def test_rejects_a_non_rgba_array(self):
        with pytest.raises(ValueError, match="HxWx4"):
            refine_cutout(np.zeros((H, W, 3), np.uint8))
