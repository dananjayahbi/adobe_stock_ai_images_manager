"""Auto-fix engine for acceptance issues.

Two modes, both reusing the Stage 4 pixel recipe so the automatic and
operator-initiated paths can never disagree about what a correction should be:

* :func:`auto_fix_image` - **single pass**. Applies the recipe once. Fast, and
  the right choice when the image is close to compliant.
* :func:`auto_fix_adaptive` - **deep fix**. Escalates the correction strength
  across repeated passes until every auto-fixable score dimension reaches the
  operator's target, logging each decision. This is the mode that can actually
  move the acceptance score, because the single-pass recipe is idempotent.

Supporting modules:

* :mod:`services.autofix.colour` - sRGB colour-space conversion.
* :mod:`services.autofix.container` - container-level (colour profile) fixes.
* :mod:`services.autofix.targets` - per-dimension goals and progress tracking.
* :mod:`services.autofix.run_log` - the structured decision log.
"""

from services.autofix.adaptive import (
    ESCALATION_STEP,
    MAX_ADAPTIVE_PASSES,
    AdaptiveResult,
    auto_fix_adaptive,
)
from services.autofix.colour import ColourConversion, convert_to_srgb
from services.autofix.container import (
    ContainerFixOutcome,
    apply_container_fixes,
    needs_srgb_fix,
)
from services.autofix.engine import DEFAULT_MAX_PASSES, AutoFixResult, auto_fix_image
from services.autofix.run_log import RunLog
from services.autofix.targets import (
    DEFAULT_TARGET,
    MAX_TARGET,
    MIN_TARGET,
    DimensionTarget,
    TargetProgress,
    clamp_target,
    diagnose_stuck,
    dimensions_from_report,
)

__all__ = [
    "AdaptiveResult",
    "AutoFixResult",
    "ColourConversion",
    "ContainerFixOutcome",
    "DEFAULT_MAX_PASSES",
    "DEFAULT_TARGET",
    "DimensionTarget",
    "ESCALATION_STEP",
    "MAX_ADAPTIVE_PASSES",
    "MAX_TARGET",
    "MIN_TARGET",
    "RunLog",
    "TargetProgress",
    "apply_container_fixes",
    "auto_fix_adaptive",
    "auto_fix_image",
    "clamp_target",
    "convert_to_srgb",
    "diagnose_stuck",
    "dimensions_from_report",
    "needs_srgb_fix",
]
