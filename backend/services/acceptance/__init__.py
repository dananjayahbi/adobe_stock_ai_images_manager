"""Acceptance scoring primitives for Adobe Stock compliance.

This package turns pixel measurements into a single 0..1 *acceptance score*
plus a list of machine-readable issue codes. The score drives two things:

* Stage 4 (Refiner) - the issue codes select the corrective recipe.
* Stage 5 (Compatibility gate) - the score is compared to a threshold.

Sub-modules
-----------
``types``          Shared dataclasses and issue-code constants.
``pixel_metrics``  Deterministic OpenCV/Pillow measurements.
``scorer``         Aggregation, weighting, and threshold evaluation.
"""

from services.acceptance.scorer import score_image
from services.acceptance.types import (
    ISSUE_CODES,
    AcceptanceReport,
    Issue,
    SubScore,
)

__all__ = [
    "ISSUE_CODES",
    "AcceptanceReport",
    "Issue",
    "SubScore",
    "score_image",
]
