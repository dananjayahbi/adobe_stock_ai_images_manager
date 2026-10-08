"""Alpha edge-quality checks for background-removed PNGs (batch pipeline v2).

After a cut-out is produced the operator needs to know whether the *edges* are
usable: soft halos, jagged (stair-stepped) contours, or a wide semi-transparent
fringe all read as "cheap cut-out" and get refused downstream.

Everything here is measured on the alpha channel with pure NumPy — no model, no
network — and the metrics are deliberately simple, monotone quantities:

* **coverage**     — fraction of alpha > 128 (a near-0 or near-1 value means the
                     removal likely failed outright).
* **fringe**       — mean width, in pixels, of the 10–240 alpha transition band
                     along the object boundary. Wide = milky halo.
* **jaggedness**   — mean absolute second difference of alpha *across* the
                     boundary, normalised: a smooth matte ramps monotonically, a
                     jagged one oscillates.
* **halo**         — mean colour distance between pixels just inside the edge
                     and the object core: a background-coloured bleed shows up
                     here even when alpha looks perfect.

Verdicts are thresholds, not scores — ``pass`` / ``warn`` / ``fail`` with the
numbers attached, so the UI can explain itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

#: Transition band (0-255 alpha) counted as "edge".
BAND_LO, BAND_HI = 10, 240
#: Verdict thresholds.
FRINGE_WARN_PX, FRINGE_FAIL_PX = 6.0, 12.0
JAGGED_WARN, JAGGED_FAIL = 0.35, 0.55
HALO_WARN, HALO_FAIL = 0.22, 0.38
COVERAGE_MIN = 0.01


@dataclass
class EdgeReport:
    """Measured edge quality for one cut-out."""

    coverage: float = 0.0
    fringe_px: float = 0.0
    jaggedness: float = 0.0
    halo: float = 0.0
    verdict: str = "pass"  # pass | warn | fail
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "coverage": round(self.coverage, 4),
            "fringe_px": round(self.fringe_px, 2),
            "jaggedness": round(self.jaggedness, 3),
            "halo": round(self.halo, 3),
            "verdict": self.verdict,
            "issues": list(self.issues),
        }


def _boundary_widths(alpha: np.ndarray) -> np.ndarray:
    """Per-boundary-pixel transition width, approximated by band membership.

    Counts, for each column/row crossing, how many pixels sit in the transition
    band — a cheap stand-in for a per-contour distance transform that stays
    monotone: a wider soft edge yields a larger number.
    """
    band = (alpha > BAND_LO) & (alpha < BAND_HI)
    # Horizontal + vertical crossings through the band.
    rows = band.sum(axis=1).astype(np.float64)
    cols = band.sum(axis=0).astype(np.float64)
    active_rows = rows[rows > 0]
    active_cols = cols[cols > 0]
    all_active = np.concatenate([active_rows, active_cols]) if (
        active_rows.size or active_cols.size
    ) else np.array([0.0])
    return all_active


def _jaggedness(alpha: np.ndarray) -> float:
    """Oscillation of alpha across the boundary, 0 (smooth ramp) → 1 (noise)."""
    # Work on rows that actually cross the object.
    lo = (alpha <= BAND_LO).any(axis=1) & (alpha >= BAND_HI).any(axis=1)
    if not lo.any():
        return 0.0
    band_rows = alpha[lo]
    # Second difference along each row: a monotone ramp has a stable second
    # difference; a jagged contour alternates sign with large magnitude.
    d2 = np.diff(band_rows, n=2, axis=1)
    if d2.size == 0:
        return 0.0
    oscillation = np.mean(np.abs(d2)) / 64.0  # 64/255 ≈ quarter-scale jumps
    return float(min(1.0, oscillation))


def _halo(rgba: np.ndarray, alpha: np.ndarray) -> float:
    """Colour shift between the object core and pixels just inside the edge."""
    core = alpha >= 250
    inner = (alpha >= 200) & (alpha < 250)
    if core.sum() < 16 or inner.sum() < 4:
        return 0.0
    core_mean = rgba[core][:, :3].mean(axis=0)
    inner_mean = rgba[inner][:, :3].mean(axis=0)
    distance = np.linalg.norm(core_mean - inner_mean) / (255.0 * np.sqrt(3.0))
    return float(min(1.0, distance))


def check_edges(path: str | Path) -> EdgeReport:
    """Measure the alpha edge quality of one RGBA PNG."""
    report = EdgeReport()
    try:
        with Image.open(path) as img:
            rgba = np.asarray(img.convert("RGBA"), dtype=np.float64)
    except Exception as exc:  # noqa: BLE001 - report, don't raise
        report.verdict = "fail"
        report.issues.append(f"Could not read the cut-out: {exc}")
        return report

    alpha = rgba[:, :, 3]
    report.coverage = float((alpha > 128).mean())

    if report.coverage < COVERAGE_MIN:
        report.verdict = "fail"
        report.issues.append("The cut-out is empty (no opaque pixels).")
        return report
    if report.coverage > 0.995:
        report.verdict = "warn"
        report.issues.append("Nothing was removed — the image is fully opaque.")

    widths = _boundary_widths(alpha)
    report.fringe_px = float(widths.mean()) if widths.size else 0.0
    report.jaggedness = _jaggedness(alpha)
    report.halo = _halo(rgba, alpha)

    if report.fringe_px >= FRINGE_FAIL_PX:
        report.issues.append(
            f"Wide semi-transparent fringe ({report.fringe_px:.1f}px) — milky halo."
        )
        report.verdict = "fail"
    elif report.fringe_px >= FRINGE_WARN_PX:
        report.issues.append(f"Noticeable edge fringe ({report.fringe_px:.1f}px).")
        report.verdict = report.verdict if report.verdict == "fail" else "warn"

    if report.jaggedness >= JAGGED_FAIL:
        report.issues.append("Jagged (stair-stepped) contour.")
        report.verdict = "fail"
    elif report.jaggedness >= JAGGED_WARN:
        report.issues.append("Slightly rough contour.")
        report.verdict = report.verdict if report.verdict == "fail" else "warn"

    if report.halo >= HALO_FAIL:
        report.issues.append("Background colour bleeds into the object edge.")
        report.verdict = "fail"
    elif report.halo >= HALO_WARN:
        report.issues.append("Mild colour shift at the edge.")
        report.verdict = report.verdict if report.verdict == "fail" else "warn"

    if not report.issues:
        report.issues.append("Edges are clean.")
    return report
