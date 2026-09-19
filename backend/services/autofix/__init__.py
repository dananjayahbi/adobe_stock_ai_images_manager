"""Auto-fix engine for acceptance issues.

Public surface:

* :func:`auto_fix_image` - correct everything automatically correctable, then
  re-score.
* :func:`apply_container_fixes` - container-level (colour profile) corrections.
* :func:`convert_to_srgb` - decode a file into sRGB pixels.

The engine deliberately reuses the Stage 4 pixel recipe rather than defining its
own corrections, so the automatic path and the operator-initiated path can never
disagree about what a given issue needs.
"""

from services.autofix.colour import ColourConversion, convert_to_srgb
from services.autofix.container import (
    ContainerFixOutcome,
    apply_container_fixes,
    needs_srgb_fix,
)
from services.autofix.engine import DEFAULT_MAX_PASSES, AutoFixResult, auto_fix_image

__all__ = [
    "AutoFixResult",
    "ColourConversion",
    "ContainerFixOutcome",
    "DEFAULT_MAX_PASSES",
    "apply_container_fixes",
    "auto_fix_image",
    "convert_to_srgb",
    "needs_srgb_fix",
]
