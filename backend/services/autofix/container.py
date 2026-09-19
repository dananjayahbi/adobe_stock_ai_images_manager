"""Container-level (non-pixel) auto-fixes.

Most acceptance issues are pixel problems and belong to
:mod:`services.refine.recipe`. A few are properties of the *file container*
instead - the colour profile is the important one, because a wrong profile
changes how every pixel is *interpreted* rather than what the pixels are.

These fixes are deliberately separate from the pixel recipe: the recipe's
corrections are strength-scaled and capped to stay inside Adobe's
"no overprocessing" guidance, whereas re-tagging or converting a colour space
is a discrete, all-or-nothing operation.

The colour conversion is driven from the **file**, not from a decoded array,
because the source ICC profile only exists in the file. Reading it is what makes
the difference between correctly *mapping* Adobe RGB pixels into sRGB and merely
*mislabelling* them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from services.acceptance.types import NOT_SRGB, Issue
from services.autofix.colour import ColourConversion, convert_to_srgb


@dataclass
class ContainerFixOutcome:
    """Result of applying every container-level fix an image needs."""

    #: BGR array (OpenCV order) ready for the pixel recipe and the JPEG writer.
    #: None when the file could not be decoded.
    image_bgr: np.ndarray | None
    #: Issue codes this pass resolved.
    addressed: list[str] = field(default_factory=list)
    #: Human-readable description of each change, for the UI.
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.addressed)


def needs_srgb_fix(issues: list[Issue]) -> bool:
    """True when the report raised any sRGB/colour-profile issue."""
    return any(issue.code == NOT_SRGB for issue in issues)


def apply_container_fixes(source: Path, issues: list[Issue]) -> ContainerFixOutcome:
    """Decode ``source`` and apply the container corrections ``issues`` implies.

    The only container correction today is the sRGB colour space, covering both
    of its failure modes: an untagged file (re-tagged) and a file carrying a
    non-sRGB profile (transformed through LittleCMS).

    Returns an outcome whose ``image_bgr`` is the array the rest of the auto-fix
    pipeline should work on.
    """
    conversion: ColourConversion | None = convert_to_srgb(source)
    if conversion is None:
        return ContainerFixOutcome(None, notes=["Could not decode the file."])

    # ``convert_to_srgb`` yields RGB (Pillow's order); the refiner, the sRGB
    # writer, and OpenCV all use BGR.
    image_bgr = np.ascontiguousarray(conversion.image_rgb[:, :, ::-1])

    if not needs_srgb_fix(issues):
        return ContainerFixOutcome(image_bgr)

    return ContainerFixOutcome(
        image_bgr,
        addressed=[NOT_SRGB],
        notes=[conversion.reason],
    )
