"""Stage 6: the dual-matte stress test.

Adobe inspects a cut-out on **both** a white and a black canvas, so "does it
look fine on my dark UI" is not the question. This module answers the question
the reviewer asks:

* **Does the contour stair-step?** Measured geometrically from the alpha's own
  contour — the fraction of turns sharper than 45°. A smooth ramp turns
  gradually (a circle of radius 500px turns 45° only eight times per lap); a
  noisy, aliased boundary zig-zags, and the ratio jumps.
* **Does the edge still carry the old backdrop?** Every soft-edge pixel is
  compared with the *nearest solid foreground colour*. A residual that leans
  brighter than the subject is a light fringe on the black matte; a residual
  that leans darker is a dark halo on the white matte. Which side of the
  residual it falls on tells the operator which canvas will expose it.

Both numbers are reported next to the existing ``edge_quality`` metrics, and
the combined verdict is the *worst* of the two, so nothing is downgraded by
averaging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..edge_quality import check_edges
from .defringe import nearest_colour

#: Trimap-independent alpha band treated as "soft edge".
BAND_LO, BAND_HI = 16, 250
#: Contour turn sharper than this counts as a stair-step (degrees).
TURN_DEG = 45.0
#: Shared alpha coverage below which there is nothing to inspect.
COVERAGE_MIN = 0.01

#: Verdict thresholds for the added metrics.
JAGGED_WARN, JAGGED_FAIL = 0.15, 0.30
HALO_WARN, HALO_FAIL = 0.16, 0.34


@dataclass
class DualMatteReport:
    """What the black/white stress test found for one cut-out."""

    contour_jaggedness: float = 0.0
    halo_black: float = 0.0  # light fringe, visible on the black canvas
    halo_white: float = 0.0  # dark fringe, visible on the white canvas
    exposed_on: str = "none"  # none | black | white | both
    edge_energy_black: float = 0.0
    edge_energy_white: float = 0.0
    band_px: int = 0
    verdict: str = "pass"  # pass | warn | fail
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "contour_jaggedness": round(self.contour_jaggedness, 3),
            "halo_black": round(self.halo_black, 3),
            "halo_white": round(self.halo_white, 3),
            "exposed_on": self.exposed_on,
            "edge_energy_black": round(self.edge_energy_black, 2),
            "edge_energy_white": round(self.edge_energy_white, 2),
            "band_px": int(self.band_px),
            "verdict": self.verdict,
            "issues": list(self.issues),
        }


def _luma(rgb: np.ndarray) -> np.ndarray:
    """Rec.601 luma along the last axis; already-1-D maps pass through.

    Handles HxW, HxWx3/4 and the flat (N, 3) slices the halo probe builds, so
    a 2-D colour array is never mistaken for a luma plane.
    """
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.ndim >= 2 and arr.shape[-1] in (3, 4):
        return 0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]
    return arr


def contour_jaggedness(alpha: np.ndarray, *, min_points: int = 16) -> float:
    """Fraction of contour turns sharper than :data:`TURN_DEG` (0-1)."""
    binary = (np.asarray(alpha) > 127).astype(np.uint8)
    if binary.sum() < 32:
        return 0.0
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    turns = 0
    sharp = 0
    for contour in contours:
        pts = contour.reshape(-1, 2).astype(np.float64)
        if len(pts) < min_points:
            continue
        delta = np.roll(pts, -1, axis=0) - pts
        heading = np.arctan2(delta[:, 1], delta[:, 0])
        turn = np.diff(np.concatenate([heading, heading[:1]]))
        turn = (turn + np.pi) % (2 * np.pi) - np.pi
        turns += turn.size
        sharp += int(np.count_nonzero(np.abs(turn) > np.radians(TURN_DEG)))
    if turns == 0:
        return 0.0
    return float(sharp) / float(turns)


def _residual_halo(
    rgb: np.ndarray, alpha: np.ndarray, solid: np.ndarray, band: np.ndarray
) -> tuple[float, float]:
    """Directional colour drift of the soft edge vs. the nearest solid pixel.

    Returns ``(halo_black, halo_white)``: the alpha-weighted share of the
    residual that leans brighter (shows on black) or darker (shows on white).
    """
    band_px = int(np.count_nonzero(band))
    solid_px = int(np.count_nonzero(solid))
    if band_px < 8 or solid_px < 64:
        return 0.0, 0.0

    local, reached = nearest_colour(rgb, solid, band, max_reach=8.0)
    if reached.sum() < 8:
        return 0.0, 0.0

    idx = np.flatnonzero(band)[reached]
    observed = np.asarray(rgb, dtype=np.float64).reshape(-1, 3)[idx]
    reference = local[reached].astype(np.float64)
    weight = np.asarray(alpha, dtype=np.float64).reshape(-1)[idx] / 255.0

    residual = _luma(observed) - _luma(reference)
    denom = float(weight.sum()) * 255.0
    if denom <= 0:
        return 0.0, 0.0

    bright = float((weight * np.clip(residual, 0.0, None)).sum() / denom)
    dark = float((weight * np.clip(-residual, 0.0, None)).sum() / denom)
    return min(1.0, bright), min(1.0, dark)


def _composite_energy(
    rgb: np.ndarray, alpha: np.ndarray, band: np.ndarray, on_white: bool
) -> float:
    """Mean |Laplacian| of the composited luma across the soft edge."""
    a = np.asarray(alpha, dtype=np.float64) / 255.0
    lum = _luma(rgb)
    comp = a * lum + ((1.0 - a) * 255.0 if on_white else 0.0)
    lap = cv2.Laplacian(comp.astype(np.float64), cv2.CV_64F)
    values = np.abs(lap[band])
    if values.size == 0:
        return 0.0
    return float(values.mean())


def dual_matte_report(rgba: np.ndarray) -> DualMatteReport:
    """Run the stress test over an in-memory HxWx4 RGBA array."""
    arr = np.asarray(rgba)
    report = DualMatteReport()
    if arr.ndim != 3 or arr.shape[2] != 4:
        report.verdict = "fail"
        report.issues.append("Not an RGBA image.")
        return report

    alpha = arr[..., 3].astype(np.float64)
    rgb = arr[..., :3]
    coverage = float((alpha > 128).mean())
    if coverage < COVERAGE_MIN:
        report.verdict = "fail"
        report.issues.append("The cut-out is empty (no opaque pixels).")
        return report

    solid = alpha >= BAND_HI
    band = (alpha > BAND_LO) & (alpha < BAND_HI)
    report.band_px = int(np.count_nonzero(band))

    report.contour_jaggedness = contour_jaggedness(alpha)
    report.halo_black, report.halo_white = _residual_halo(rgb, alpha, solid, band)
    report.exposed_on = _exposed_on(report.halo_black, report.halo_white)
    report.edge_energy_black = _composite_energy(rgb, alpha, band, on_white=False)
    report.edge_energy_white = _composite_energy(rgb, alpha, band, on_white=True)

    _verdict(report)
    return report


def _exposed_on(black: float, white: float) -> str:
    hi_black, hi_white = black >= HALO_WARN, white >= HALO_WARN
    if hi_black and hi_white:
        return "both"
    if hi_black:
        return "black"
    if hi_white:
        return "white"
    return "none"


def _escalate(report: DualMatteReport, level: int, issue: str) -> None:
    order = {"pass": 0, "warn": 1, "fail": 2}
    if order[level] > order[report.verdict]:
        report.verdict = level
    report.issues.append(issue)


def _verdict(report: DualMatteReport) -> None:
    if report.contour_jaggedness >= JAGGED_FAIL:
        _escalate(report, "fail", "Stair-stepped contour (alpha boundary zig-zags).")
    elif report.contour_jaggedness >= JAGGED_WARN:
        _escalate(report, "warn", "Slightly rough contour at 100% zoom.")

    if max(report.halo_black, report.halo_white) >= HALO_FAIL:
        _escalate(report, "fail", f"Visible fringe on the {_named(report)} matte.")
    elif max(report.halo_black, report.halo_white) >= HALO_WARN:
        _escalate(report, "warn", f"Faint fringe on the {_named(report)} matte.")

    if not report.issues:
        report.issues.append("Clean on both mattes.")


def _named(report: DualMatteReport) -> str:
    if report.exposed_on == "both":
        return "black and white"
    if report.exposed_on == "none":
        return "inspection"
    return report.exposed_on


def _worst(*verdicts: str) -> str:
    order = {"pass": 0, "warn": 1, "fail": 2}
    return max(verdicts, key=lambda v: order.get(v, 2))


def audit(path: str | Path) -> dict:
    """Full cut-out audit: base edge metrics + the dual-matte stress test.

    The returned dict keeps ``edge_quality`` (unchanged contract) and adds
    ``dual_matte``; ``verdict`` / ``issues`` at the top level are the union of
    both, worst-first, so a caller reading only those cannot miss a finding.
    """
    base = check_edges(path)
    payload = base.to_dict()
    payload.pop("verdict", None)
    payload.pop("issues", None)

    try:
        with Image.open(path) as img:
            rgba = np.asarray(img.convert("RGBA"), dtype=np.uint8)
        dual = dual_matte_report(rgba)
    except Exception as exc:  # noqa: BLE001 - a bad file must not raise
        dual = DualMatteReport(verdict="fail", issues=[f"Could not read the cut-out: {exc}"])

    payload["dual_matte"] = dual.to_dict()
    payload["verdict"] = _worst(base.verdict, dual.verdict)
    issues = [i for i in (*base.issues, *dual.issues) if i != "Edges are clean."]
    payload["issues"] = issues or ["Edges are clean on both mattes."]
    return payload


__all__ = [
    "DualMatteReport",
    "audit",
    "contour_jaggedness",
    "dual_matte_report",
]
